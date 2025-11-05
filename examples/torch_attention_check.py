import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.utils.benchmark as benchmark
from torch.nn.attention import SDPBackend, sdpa_kernel

# Example Usage:
# query = torch.randn(2, 3, 8, device=device)
# key = torch.randn(2, 3, 8, device=device)
# value = torch.randn(2, 3, 8, device=device)
# F.scaled_dot_product_attention(query, key, value)

def benchmark_torch_ms(f, *args, **kwargs):
    t0 = benchmark.Timer(
        stmt = "f(*args, **kwargs)", globals={"args": args, "kwargs": kwargs, "f": f}
    )
    # get execution time
    ret = t0.blocked_autorange().mean * 1e6
    return ret


def exec_test(is_enabled,
              name,
              val_reference,
              query,
              key,
              value):
    ret = None

    if is_enabled:
        try:
            # first run of function to get the execution time
            exec_ms = benchmark_torch_ms(F.scaled_dot_product_attention, query, key, value)
            # second run of function to get the value from the executed function
            ret = F.scaled_dot_product_attention(query, key, value)
            if ret is not None:
                if val_reference is not None:
                    # Verify that the result is close to reference_value calculated with SDPBackend.Math
                    try:
                        torch.testing.assert_close(ret, val_reference)
                        print(f"    success:   value matches with the reference value from SDPBackend.Math")
                        print(f"    exec time: {exec_ms:.3f} ms")
                        print(f"    res.shape: {ret.shape}")
                    except AssertionError as e:
                        print(f"{name} error, incorrect value for scaled_dot_product_attention: {e}")
                        for row in ret:
                            print(row)
                else:
                    print(f"    success:   reference value calculated with SDPBackend.Math")
                    print(f"    exec time: {exec_ms:.3f} ms")
                    print(f"    res.shape: {ret.shape}")
            else:
                print(f"{name} error, failed to calculate scaled_dot_product_attention")
        except RuntimeError as ex:
            print(f"{name} error: {ex}")
    else:
        print(f"{name} not enabled")
    return ret

def benchmark_sdb_backend(device:str, dtype):
    val_reference = None
    # hyper-parameters
    batch_size = 16
    num_heads = 16
    max_sequence_len = 64
    embed_dimension = 128

    query = torch.rand(batch_size,
                   num_heads,
                   max_sequence_len,
                   embed_dimension,
                   device=device,
                   dtype=dtype)
    key = torch.rand(batch_size,
                 num_heads,
                 max_sequence_len,
                 embed_dimension,
                 device=device,
                 dtype=dtype)
    value = torch.rand(batch_size,
                   num_heads,
                   max_sequence_len,
                   embed_dimension,
                   device=device,
                   dtype=dtype)
    F.scaled_dot_product_attention(query, key, value)

    with sdpa_kernel(SDPBackend.MATH):
        name = str(SDPBackend.MATH)
        print("----------")
        print(name + " test started")
        try:
            is_enabled = torch.backends.cuda.math_sdp_enabled()
            val_reference = exec_test(is_enabled, name, None, query, key, value)
        except RuntimeError as ex:
            print(f"{name} error support check failed: {ex}")
        print(name + " test done")
    
    with sdpa_kernel(SDPBackend.EFFICIENT_ATTENTION):
        name = str(SDPBackend.EFFICIENT_ATTENTION)
        print("----------")
        print(name + " test started")
        try:
            is_enabled = torch.backends.cuda.mem_efficient_sdp_enabled()
            exec_test(is_enabled, name, val_reference, query, key, value)
        except RuntimeError as ex:
            print(f"{name} error support check failed: {ex}")
        print(name + " test done")
    
    
    with sdpa_kernel(SDPBackend.FLASH_ATTENTION):
        name = str(SDPBackend.FLASH_ATTENTION)
        print("----------")
        print(name + " test started")
        try:
            is_enabled = torch.backends.cuda.flash_sdp_enabled()
            exec_test(is_enabled, name, val_reference, query, key, value)
        except RuntimeError as ex:
            print(f"{name} error support check failed: {ex}")
        print(name + " test done")

    name = "SDPBackend.Default"
    print("----------")
    print(name + " test started")
    try:
        is_enabled = torch.backends.cuda.math_sdp_enabled()
        exec_test(is_enabled, name, val_reference, query, key, value)
    except RuntimeError as ex:
        print(f"{name} error support check failed: {ex}")
    print(name + " test done")


def main():
    dtype = torch.float16
    device = "cpu"
    if torch.cuda.is_available():
        device = "cuda"
    benchmark_sdb_backend(device, dtype)

if __name__ == "__main__":
    main()
