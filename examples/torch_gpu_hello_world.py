import torch

print("Pytorch version: " + torch.__version__)
print("ROCM HIP version: " + torch.version.hip)
print("Default cuda device name: " + torch.cuda.get_device_name())
X_train = torch.FloatTensor([0.0, 1.0, 2.0])
dev_cnt=torch.cuda.device_count()
print("cuda device count: " + str(dev_cnt))
err_devices = ""
for ii in range(dev_cnt):
    try:
        print("cuda:" + str(ii) + " device name: " + torch.cuda.get_device_name(ii))
        if torch.cuda.is_available():
            device = torch.device("cuda:" + str(ii))
        else:
            device = torch.device("cpu")
        print("device type: " + str(device))
        X_train = torch.FloatTensor([0.0, 1.0, 2.0])
        X_train = X_train.to(device)
        print("Tensor training running on cuda: " + str(X_train.is_cuda))
        print("Running simple model training test")
        print("    " + str(X_train))
    except Exception as e:
        if not err_devices:
            err_devices =  torch.cuda.get_device_name(ii)
        else:
            err_devices = err_devices + ", " +  torch.cuda.get_device_name(ii)
        print(f"An error occurred with {str(device)}:")
        print(f"    {e}")
if err_devices:
    print(f"\nTorch GPU Hello World, test failures on {err_devices}")
else:
    print("\nTorch GPU Hello World, test finished succesfully")
