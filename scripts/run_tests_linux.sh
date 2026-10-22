#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -U pip
  .venv/bin/pip install -e ".[dev]"
fi
.venv/bin/pytest -q tests/python
dotnet build src/desktop/MainBrain.Contracts/MainBrain.Contracts.csproj -c Release
dotnet test tests/dotnet/MainBrain.Contracts.Tests/MainBrain.Contracts.Tests.csproj -c Release
echo "Linux pārbaudes pabeigtas."
