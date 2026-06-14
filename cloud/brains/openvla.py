"""OpenVLA Brain — Vision-Language-Action model on GPU.

Uses the OpenVLA model (openvla/openvla-7b) from HuggingFace to map
camera frames + natural-language commands to discrete rover actions.

The model outputs a 7-DoF continuous action vector (delta xyz, delta rpy,
gripper). We map the dominant translational component to our discrete
action space: FORWARD / LEFT / RIGHT / STOP.

Memory:
    OpenVLA-7B in bf16 = ~14 GB — too large for an 8 GB card.
    We load in 4-bit (NF4) quantization via bitsandbytes, which
    brings VRAM usage to ~5 GB and leaves headroom for inference.

Requirements:
    - NVIDIA GPU with >=8 GB VRAM (RTX 3070 or better)
    - Python 3.11, PyTorch 2.4.1 with CUDA 12.4
    - transformers, accelerate, bitsandbytes, Pillow
"""

import time
import numpy as np
from PIL import Image

import sys, os
_root = os.path.join(os.path.dirname(__file__), "..", "..")
if _root not in sys.path:
    sys.path.insert(0, _root)

from cloud.brains.base import Brain
from shared.protocol import Action, BrainResult

MODEL_ID = "openvla/openvla-7b"
DEFAULT_COMMAND = "navigate forward and avoid obstacles"

# Thresholds for mapping continuous actions → discrete
FORWARD_THRESHOLD = 0.15   # min forward delta to count as FORWARD
TURN_THRESHOLD = 0.10      # min lateral delta to count as LEFT/RIGHT


class OpenVLABrain(Brain):

    name = "openvla"

    def __init__(self):
        self.processor = None
        self.model = None
        self.device = None

    def startup(self):
        import torch
        from transformers import AutoModelForVision2Seq, AutoProcessor, BitsAndBytesConfig

        if not torch.cuda.is_available():
            raise RuntimeError(
                "OpenVLA requires a CUDA GPU. No GPU found. "
                "Install PyTorch with CUDA: pip install torch==2.4.1 "
                "--index-url https://download.pytorch.org/whl/cu124"
            )

        self.device = torch.device("cuda")
        vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
        gpu_name = torch.cuda.get_device_name(0)
        print(f"  GPU: {gpu_name} ({vram_gb:.1f} GB)")

        # 4-bit quantization — required for 8 GB cards (3070, etc.)
        # Reduces ~14 GB bf16 model to ~5 GB VRAM.
        quant_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_quant_type="nf4",
        )

        print(f"  Loading {MODEL_ID} in 4-bit (NF4) quantization...")
        print(f"  (first run downloads ~14 GB of weights)")
        self.processor = AutoProcessor.from_pretrained(
            MODEL_ID, trust_remote_code=True,
        )
        self.model = AutoModelForVision2Seq.from_pretrained(
            MODEL_ID,
            quantization_config=quant_config,
            device_map="auto",
            low_cpu_mem_usage=True,
            trust_remote_code=True,
        )
        self.model.eval()

        vram_used = torch.cuda.memory_allocated() / 1e9
        print(f"  ✓ OpenVLA loaded on {self.device} ({vram_used:.1f} GB VRAM used)")

    def _predict_action(self, frame: np.ndarray, command: str) -> np.ndarray:
        """Run VLA inference. Returns 7-DoF action vector."""
        import torch

        pil_image = Image.fromarray(frame)
        prompt = f"In: What action should the robot take to {command}?\nOut:"

        inputs = self.processor(prompt, pil_image).to(
            self.device, dtype=torch.bfloat16,
        )

        with torch.no_grad():
            action = self.model.predict_action(
                **inputs, unnorm_key="bridge_orig", do_sample=False,
            )

        return action.cpu().numpy() if hasattr(action, "cpu") else np.array(action)

    def _discretize(self, action_vec: np.ndarray) -> tuple[Action, str]:
        """Map 7-DoF continuous action to discrete rover action.

        OpenVLA outputs [dx, dy, dz, drx, dry, drz, gripper].
        For a ground rover:
          dx = forward/backward
          dy = left/right lateral
          dz, dr*, gripper = ignored
        """
        dx = float(action_vec[0])  # forward (+) / backward (-)
        dy = float(action_vec[1])  # left (+) / right (-)

        # Dominant axis wins
        if abs(dy) > abs(dx) and abs(dy) > TURN_THRESHOLD:
            if dy > 0:
                return Action.LEFT, f"lateral dy={dy:.3f} → LEFT"
            else:
                return Action.RIGHT, f"lateral dy={dy:.3f} → RIGHT"
        elif dx > FORWARD_THRESHOLD:
            return Action.FORWARD, f"forward dx={dx:.3f} → FORWARD"
        elif dx < -FORWARD_THRESHOLD:
            return Action.STOP, f"backward dx={dx:.3f} → STOP (no reverse)"
        else:
            return Action.STOP, f"small motion dx={dx:.3f} dy={dy:.3f} → STOP"

    def act(self, frame: np.ndarray, command: str = "") -> BrainResult:
        if not command:
            command = DEFAULT_COMMAND

        t0 = time.monotonic()
        try:
            action_vec = self._predict_action(frame, command)
            action, reasoning = self._discretize(action_vec)
            inference_ms = (time.monotonic() - t0) * 1000

            return BrainResult(
                action=action,
                detections=[],
                reasoning=f"OpenVLA: {reasoning} (raw={action_vec[:3].tolist()})",
                inference_ms=inference_ms,
                brain_name=self.name,
            )
        except Exception as e:
            inference_ms = (time.monotonic() - t0) * 1000
            return BrainResult(
                action=Action.STOP,
                detections=[],
                reasoning=f"OpenVLA error: {e}",
                inference_ms=inference_ms,
                brain_name=self.name,
            )

    def shutdown(self):
        self.model = None
        self.processor = None
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
