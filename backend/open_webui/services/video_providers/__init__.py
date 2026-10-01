"""Explicit registry: model runtimes belong in external services, not WebUI."""

from .heygen import HeyGen
from .local_h3 import LocalH3

PROVIDERS = {'heygen': HeyGen, 'local_h3': LocalH3}


def provider_for(name, config):
    if name not in PROVIDERS:
        raise ValueError('视频引擎尚未安装')
    return PROVIDERS[name](config)
