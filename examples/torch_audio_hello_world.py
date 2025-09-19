import torch
import torchaudio

print("pytorch version: " + torch.__version__)
print("pytorch audio version: " + torchaudio.__version__)

try:
    import torchcodec
    print("torchcodec version: " + torchcodec.__version__)
except ImportError:
    print("Could not find torchcodec module")
