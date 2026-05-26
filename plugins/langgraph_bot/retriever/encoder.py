"""文本编码 — Sentence-BERT 向量化。"""

import os
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from nonebot.log import logger

MODEL_NAME = "BAAI/bge-small-zh-v1.5"

# HF 镜像（国内加速），通过 mihomo 代理也可用
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

_encoder: SentenceTransformer | None = None
_tokenizer = None
_model = None


def get_encoder() -> SentenceTransformer:
    """懒加载编码器（进程级单例）。ST 仅用于加载模型权重，不走其 encode()（避免 5.x to/eval 递归 bug）。"""
    global _encoder, _tokenizer, _model
    if _encoder is None:
        logger.info(f"[retriever] loading model: {MODEL_NAME}")
        _encoder = SentenceTransformer(MODEL_NAME)
        _tokenizer = _encoder.tokenizer
        _model = _encoder.transformers_model
        _model.eval()
        logger.info("[retriever] model loaded")
    return _encoder


def encode(texts: list[str]) -> np.ndarray:
    """将文本列表编码为归一化向量矩阵。绕过 ST encode()，直接调用底层 model forward。"""
    get_encoder()
    with torch.no_grad():
        batch = _tokenizer(
            texts, padding=True, truncation=True, max_length=512, return_tensors="pt"
        )
        # BGE 模型取 [CLS] token 的输出做句子向量
        outputs = _model(**batch)
        if hasattr(outputs, "last_hidden_state"):
            hidden = outputs.last_hidden_state
        elif isinstance(outputs, dict):
            hidden = outputs.get("last_hidden_state")
        else:
            hidden = outputs[0]
        # [CLS] pooling
        vecs = hidden[:, 0, :]
        # L2 normalize
        vecs = torch.nn.functional.normalize(vecs, p=2, dim=1)
        return vecs.cpu().numpy().astype(np.float32)
