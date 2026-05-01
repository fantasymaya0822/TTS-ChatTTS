# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = []
datas += collect_data_files("imageio_ffmpeg")
datas += collect_data_files("ChatTTS")

hiddenimports = []
hiddenimports += collect_submodules("edge_tts")
hiddenimports += collect_submodules("aiohttp")
hiddenimports += collect_submodules("charset_normalizer")
hiddenimports += collect_submodules("ChatTTS")
hiddenimports += collect_submodules("torch")
hiddenimports += collect_submodules("torchaudio")
hiddenimports += collect_submodules("transformers")
hiddenimports += collect_submodules("huggingface_hub")

a = Analysis(
    ["novel_tts/gui.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NovelChatTTS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="NovelChatTTS",
)
