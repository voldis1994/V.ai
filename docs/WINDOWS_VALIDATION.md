# WINDOWS_VALIDATION

**Statuss šajā sesijā:** Windows GUI/UIA/Capture/WebView2 E2E ir **BLOĶĒTS** (izstrāde Linux CI).

## Kas ir ieviests Windows izpildei

| Komponente | Faili | Statuss |
|------------|-------|---------|
| UI Automation (UIA3/FlaUI) | `UiAutomationService.cs` | IEVIESTS — bez fake invoked |
| SendInput | `InputService.cs` | IEVIESTS — klikšķi/teksts/īsceļi + STOP |
| Logu uztveršana | `WindowCaptureService.cs` | IEVIESTS — PrintWindow/BitBlt + PNG; `live_image` tikai ar kadru |
| Tool Bridge | `ToolBridgeServer.cs` + `tools/bridge.py` | IEVIESTS |
| WebView2 operācijas | `BrowserAutomationService.cs` | IEVIESTS |
| Focus/Multi UI | `MainWindow.xaml`, `MainViewModel.cs` | IEVIESTS |

## Obligātās Windows komandas

```powershell
./scripts/setup_windows.ps1
dotnet build MainBrainOS.sln -c Release
./scripts/run_acceptance.ps1
./scripts/build_release.ps1
# Palaist release\win-x64\MainBrain.exe ĀRPUS repo
```

## Pieņemšanas testi D–H, L

Skatīt `tests/e2e/README.md` un `docs/RELEASE_VERIFICATION.md`.  
Šajā vidē rezultāts: **BLOĶĒTS** — nav Windows runtime.
