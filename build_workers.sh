#!/usr/bin/env bash
# Builds the compiled probing workers into ./bin and (optionally) lets them open raw ICMP sockets.
#
#   ./build_workers.sh              build Go + Rust, then setcap (asks for sudo)
#   ./build_workers.sh --no-setcap  build only
#
# Run it as your normal user (not with sudo): only the setcap step needs privileges.
# The dashboard itself runs as root, so setcap is only needed if you run the workers by hand.
set -uo pipefail
cd "$(dirname "$0")"
ROOT=$PWD
BIN=$ROOT/bin
DO_SETCAP=1
[[ "${1:-}" == "--no-setcap" ]] && DO_SETCAP=0

# Common user-level install locations (go.dev tarball in ~/go-toolchain, rustup in ~/.cargo).
for d in "$HOME/go-toolchain/go/bin" "/usr/local/go/bin" "$HOME/go/bin" "$HOME/.cargo/bin"; do
    [[ -d $d ]] && PATH="$PATH:$d"
done

mkdir -p "$BIN"
built=()

# ---- Go --------------------------------------------------------------------
if command -v go >/dev/null 2>&1; then
    echo "[go] $(go version)"
    # CGO off => fully static binary using only the standard library (fast build, no libc dependency).
    if (cd workers/go_prober && CGO_ENABLED=0 go build -trimpath -o "$BIN/go_prober" .); then
        echo "[go] built bin/go_prober"; built+=("$BIN/go_prober")
    else
        echo "[go] BUILD FAILED" >&2
    fi
else
    echo "[go] 'go' not found - skipping. Install from https://go.dev/dl/ (the Go engine will be unavailable in the dashboard)."
fi

# ---- Rust ------------------------------------------------------------------
if command -v cargo >/dev/null 2>&1 && command -v rustc >/dev/null 2>&1; then
    echo "[rust] $(rustc --version)"
    if cargo build --release --manifest-path workers/rust_prober/Cargo.toml; then
        cp workers/rust_prober/target/release/rust_prober "$BIN/rust_prober"
        echo "[rust] built bin/rust_prober"; built+=("$BIN/rust_prober")
    else
        echo "[rust] BUILD FAILED" >&2
    fi
else
    echo "[rust] 'cargo'/'rustc' not found - skipping. Install from https://rustup.rs (the Rust engine will be unavailable in the dashboard)."
fi

if ((${#built[@]} == 0)); then
    echo "Nothing was built." >&2
    exit 1
fi

# ---- capabilities ------------------------------------------------------------
# cap_net_raw lets a non-root user open SOCK_RAW sockets. The capability is stored
# on the file (an extended attribute) and must be re-applied after every rebuild.
if ((DO_SETCAP)); then
    if ! command -v setcap >/dev/null 2>&1; then
        echo "setcap not found (install libcap2-bin); run the workers as root instead."
    else
        for b in "${built[@]}"; do
            if [[ $EUID -eq 0 ]]; then setcap cap_net_raw+ep "$b"; else sudo setcap cap_net_raw+ep "$b"; fi \
                && echo "setcap cap_net_raw+ep $(basename "$b")" \
                || echo "WARNING: setcap failed for $b (workers will need sudo)" >&2
        done
    fi
fi
echo "Done: ${built[*]##*/}"
