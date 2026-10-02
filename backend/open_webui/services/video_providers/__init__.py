"""Explicit registry: model runtimes belong in external services, not WebUI."""

from .heygen import HeyGen
from .local_h3 import LocalH3, MacH3, CudaH3

H3_PROVIDERS = frozenset(('local_h3', 'h3_mac', 'h3_4090'))
PROVIDERS = {'heygen': HeyGen, 'local_h3': LocalH3, 'h3_mac': MacH3, 'h3_4090': CudaH3}


def provider_for(name, config):
    if name not in PROVIDERS:
        raise ValueError('视频引擎尚未安装')
    return PROVIDERS[name](config)
