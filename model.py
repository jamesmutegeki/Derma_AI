"""
HRNet Backbone + Concept Bottleneck Model (CBM) + XAI Layer.

Provides:
    - HRNetFeatureExtractor: multi-resolution feature extraction via timm HRNet.
    - ConceptBottleneck: maps visual features to interpretable medical concepts.
    - DermatologyCBM: end-to-end model combining HRNet, CBM, and classifier.
    - XAIExplainer: Integrated Gradients and Grad-CAM for clinical audit.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import List, Optional, Tuple

import timm


CONCEPT_NAMES = [
    "asymmetry",
    "border_irregularity",
    "color_variegation",
    "diameter_large",
    "melanin_density",
    "inflammation",
    "ulceration",
]

NUM_CONCEPTS = len(CONCEPT_NAMES)


class HRNetFeatureExtractor(nn.Module):
    """High-Resolution Net backbone that preserves fine-grained spatial detail.

    Uses timm's pretrained HRNet with ``features_only=True`` to expose
    multi-resolution feature pyramids.  The highest-resolution feature map
    (list index 0) is what we keep for the Concept Bottleneck.
    """

    def __init__(self, model_name: str = "hrnet_w18", pretrained: bool = True):
        super().__init__()
        # features_only=True returns a list of feature maps at each resolution.
        # output_stride is available for segmentation-style use.
        self.backbone = timm.create_model(
            model_name,
            pretrained=pretrained,
            features_only=True,
            out_indices=(0,),  # keep only the highest-resolution output
        )
        # Determine the channel dimension from the backbone
        self.feature_info = self.backbone.feature_info
        self.num_features = self.feature_info.channels()[0]
        self._output_stride = self.feature_info.reduction()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        features: List[torch.Tensor] = self.backbone(x)
        return features[0]  # (B, C, H/4, W/4)

    @property
    def output_stride(self) -> int:
        return self._output_stride


class ConceptBottleneck(nn.Module):
    """Maps visual embeddings to discrete medical concepts.

    The bottleneck uses a linear projection + sigmoid to produce
    interpretable concept scores (e.g., asymmetry=0.92, melanin_density=0.15)
    that a clinician can inspect before the final classification step.
    """

    def __init__(
        self,
        in_features: int,
        num_concepts: int = NUM_CONCEPTS,
        hidden_dim: Optional[int] = None,
    ):
        super().__init__()
        hidden_dim = hidden_dim or in_features // 2

        self.gap = nn.AdaptiveAvgPool2d(1)
        self.concept_net = nn.Sequential(
            nn.Linear(in_features, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(inplace=True),
            nn.Dropout(0.25),
            nn.Linear(hidden_dim, num_concepts),
        )

    def forward(self, feature_map: torch.Tensor) -> torch.Tensor:
        pooled = self.gap(feature_map).flatten(1)  # (B, in_features)
        logits = self.concept_net(pooled)           # (B, num_concepts)
        return torch.sigmoid(logits)


class DermatologyCBM(nn.Module):
    """End-to-end Concept Bottleneck Model for dermatology classification.

    Architecture:
        Input Image
           |
        HRNetBackbone              — fine-grained feature extraction
           |
        ConceptBottleneck          — predict medical concept scores
           |
        Linear Classifier (frozen / trained) — final diagnosis
           |
        class logits (benign, melanoma, kaposi_sarcoma)

    The ``concept_bottleneck`` outputs can be inspected or even *intervened*
    upon at inference time (interventional CBM).
    """

    def __init__(
        self,
        num_classes: int = 3,
        num_concepts: int = NUM_CONCEPTS,
        hrnet_name: str = "hrnet_w18",
        pretrained_backbone: bool = True,
        freeze_backbone: bool = False,
        freeze_concepts: bool = False,
    ):
        super().__init__()
        self.backbone = HRNetFeatureExtractor(hrnet_name, pretrained_backbone)
        feat_dim = self.backbone.num_features

        self.concept_bottleneck = ConceptBottleneck(feat_dim, num_concepts)
        self.classifier = nn.Linear(num_concepts, num_classes)

        if freeze_backbone:
            for p in self.backbone.parameters():
                p.requires_grad = False

        if freeze_concepts:
            for p in self.concept_bottleneck.parameters():
                p.requires_grad = False

        self._concept_names = CONCEPT_NAMES
        self.to(torch.float32)

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        fm = self.backbone(x)
        concepts = self.concept_bottleneck(fm)
        logits = self.classifier(concepts)
        return logits, concepts

    def get_concepts(self, x: torch.Tensor) -> torch.Tensor:
        _logits, concepts = self.forward(x)
        return concepts.detach()

    def get_features(self, x: torch.Tensor) -> torch.Tensor:
        return self.backbone(x)

    @property
    def concept_names(self) -> List[str]:
        return self._concept_names


class GradCAM:
    """Grad-CAM for HRNet-based models.

    Hooks into the backbone's **output** (highest-resolution feature map,
    index 0 of the multi-resolution list) rather than an internal Conv2d
    layer.  This is necessary because HRNet's internal topology uses
    parallel branches and side-path downsampling convs that may not
    receive gradients from the final loss — hooking the backbone's output
    guarantees both activations *and* gradients are captured.
    """

    def __init__(self, model: DermatologyCBM):
        self.model = model
        self.gradients: Optional[torch.Tensor] = None
        self.activations: Optional[torch.Tensor] = None
        self._register_hooks()

    def _register_hooks(self):
        backbone = self.model.backbone.backbone
        self._backward_handles = []

        def forward_hook(module, input, output):
            feat_map = output[0]
            self.activations = feat_map
            # Remove old backward handles to prevent memory leak
            for h in self._backward_handles:
                h.remove()
            self._backward_handles.clear()
            self._backward_handles.append(
                feat_map.register_hook(lambda grad: setattr(self, "gradients", grad))
            )

        self._forward_handle = backbone.register_forward_hook(forward_hook)

    def remove_hooks(self):
        self._forward_handle.remove()
        for h in self._backward_handles:
            h.remove()
        self._backward_handles.clear()

    def generate(self, x: torch.Tensor, class_idx: Optional[int] = None) -> np.ndarray:
        self.model.zero_grad()
        logits, _ = self.model(x)

        if class_idx is None:
            class_idx = logits.argmax(dim=1).item()

        score = logits[:, class_idx]
        score.backward()

        if self.gradients is None or self.activations is None:
            raise RuntimeError(
                "Grad-CAM hooks did not fire. "
                "Verify model forward/backward — ensure the input has requires_grad=True "
                "and the model is not inside a torch.no_grad() block."
            )

        weights = self.gradients.mean(dim=(2, 3), keepdim=True)
        cam = (self.activations * weights).sum(dim=1, keepdim=True)
        cam = F.relu(cam)

        cam = F.interpolate(cam, size=x.shape[2:], mode="bilinear", align_corners=False)
        cam = cam.squeeze().detach().cpu().numpy()

        cam_range = cam.max() - cam.min()
        cam = (cam - cam.min()) / max(cam_range, 1e-8)
        return cam

class XAIExplainer:
    """Explainable AI module for dermatology CBM models.

    Provides:
        - Integrated Gradients (via Captum)
        - Grad-CAM saliency maps
        - Concept attribution heatmaps
    """

    def __init__(self, model: DermatologyCBM, device: torch.device):
        self.model = model
        self.device = device
        self.gradcam = GradCAM(model)

        try:
            from captum.attr import IntegratedGradients
            self._ig = IntegratedGradients(self._forward_wrapper)
            self._captum_available = True
        except ImportError:
            self._captum_available = False

    def _forward_wrapper(self, x: torch.Tensor) -> torch.Tensor:
        logits, _ = self.model(x)
        return logits

    def integrated_gradients(
        self, x: torch.Tensor, target: Optional[int] = None, steps: int = 50
    ) -> np.ndarray:
        if not self._captum_available:
            raise ImportError("captum is required for Integrated Gradients. pip install captum")

        if target is None:
            logits, _ = self.model(x)
            target = logits.argmax(dim=1).item()

        x.requires_grad_()
        baseline = torch.zeros_like(x)

        attr, _ = self._ig.attribute(
            x,
            baselines=baseline,
            target=target,
            n_steps=steps,
            return_convergence_delta=True,
        )

        saliency = attr.squeeze().cpu().numpy()
        saliency = np.max(np.abs(saliency), axis=0)
        saliency = (saliency - saliency.min()) / max(saliency.ptp(), 1e-8)
        return saliency

    def grad_cam(self, x: torch.Tensor, class_idx: Optional[int] = None) -> np.ndarray:
        return self.gradcam.generate(x, class_idx)

    def concept_attribution(self, x: torch.Tensor) -> dict:
        """Return concept scores for interpretability."""
        _, concepts = self.model(x)
        concept_dict = {
            name: round(concepts[0, i].item(), 4)
            for i, name in enumerate(self.model.concept_names)
        }
        return concept_dict

    def cleanup(self):
        self.gradcam.remove_hooks()
