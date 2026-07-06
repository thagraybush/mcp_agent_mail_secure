"""Stub for removed share/export module. GitHub Pages publishing was stripped in the hardening fork."""

DEFAULT_CHUNK_SIZE = 50
DEFAULT_CHUNK_THRESHOLD = 100
DETACH_ATTACHMENT_THRESHOLD = 1_000_000
INLINE_ATTACHMENT_THRESHOLD = 65_536
SCRUB_PRESETS: dict = {}


class ShareExportError(Exception):
    pass


async def build_bundle_assets(*a, **kw):
    raise NotImplementedError("Share/export was removed in the hardened fork")


async def copy_viewer_assets(*a, **kw):
    raise NotImplementedError("Share/export was removed in the hardened fork")


async def create_snapshot_context(*a, **kw):
    raise NotImplementedError("Share/export was removed in the hardened fork")


def detect_hosting_hints(*a, **kw):
    return {}


async def encrypt_bundle(*a, **kw):
    raise NotImplementedError("Share/export was removed in the hardened fork")


async def package_directory_as_zip(*a, **kw):
    raise NotImplementedError("Share/export was removed in the hardened fork")


def prepare_output_directory(*a, **kw):
    raise NotImplementedError("Share/export was removed in the hardened fork")


def resolve_sqlite_database_path(*a, **kw):
    return None


async def sign_manifest(*a, **kw):
    raise NotImplementedError("Share/export was removed in the hardened fork")


async def summarize_snapshot(*a, **kw):
    return {}


async def verify_bundle(*a, **kw):
    raise NotImplementedError("Share/export was removed in the hardened fork")


async def decrypt_with_age(*a, **kw):
    raise NotImplementedError("Share/export was removed in the hardened fork")
