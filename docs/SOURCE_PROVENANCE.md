# Source provenance

This repository was assembled from the maintainers' installed YangJianJian build and locally authored application sources.

- The WPF desktop host was reconstructed from the maintainers' own signed application assembly and its symbols, then rewritten into maintainable XAML and C# source.
- Backend Python modules were taken from the maintainers' source files and, where only bytecode was present, reconstructed from the maintainers' own application package.
- The Web UI was present only as optimized ES module assets in the installed build. The original Vue project source was not available. The public repository includes the running, inspectable assets and does not claim that they are the original unminified authoring files.
- Installation binaries, customer projects, model weights, runtime downloads, local settings, credentials and logs were excluded.

The maintainers confirmed authorization to modify and open source this application.

The Windows compatibility assets in release `v2026.10.27.1` package the maintainers'
existing desktop runtime. They are not represented as a byte-for-byte rebuild
of this recovered source tree. Before distribution,
`scripts/repack-public-account.py` removes the legacy publisher username,
salt and password digest and connects the runtime to `backend/public_account.py`.
The public account implementation is shared with the source build. Installers
and portable archives retain their third-party runtime notices and licenses.
