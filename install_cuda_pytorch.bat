@echo off
echo ============================================================
echo   Installing CUDA-enabled PyTorch
echo   This will fix GPU not working issue
echo ============================================================
echo.

echo Uninstalling existing PyTorch...
pip uninstall -y torch torchvision torchaudio

echo.
echo Installing CUDA 11.8 PyTorch...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

echo.
echo Testing CUDA...
python -c "import torch; print(f'CUDA Available: {torch.cuda.is_available()}'); print(f'Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"None\"}')"

echo.
echo ============================================================
echo   Installation complete!
echo ============================================================
echo.
echo If CUDA is still not available:
echo 1. Install NVIDIA Driver
echo 2. Install CUDA Toolkit 11.8
echo 3. Restart computer
echo.
pause