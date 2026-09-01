"""Build-option models shared by configuration wizard pages."""

from enum import Enum


XNACK_CAPABLE_TARGETS = frozenset(
    {
        "gfx906",
        "gfx908",
        "gfx90a",
        "gfx942",
        "gfx950",
    }
)
ASAN_DEVICE_TARGETS = frozenset(
    {
        "gfx906",
        "gfx90a",
        "gfx942",
        "gfx950",
    }
)


class XnackMode(Enum):
    """Supported XNACK target modes for one base GPU architecture."""

    PLAIN = "plain"
    MINUS = "xnack-"
    PLUS = "xnack+"
    BOTH = "xnack- and xnack+"

    def get_display_name(self):
        """Return the human-readable name shown in the wizard.

        Example:
            XnackMode.BOTH.get_display_name() returns
            "XNACK- and XNACK+".
        """
        display_names = {
            XnackMode.PLAIN: "Plain",
            XnackMode.MINUS: "XNACK-",
            XnackMode.PLUS: "XNACK+",
            XnackMode.BOTH: "XNACK- and XNACK+",
        }
        ret = display_names[self]
        return ret

    def get_target_values(self, base_target):
        """Return config targets represented by this XNACK mode.

        Example:
            XnackMode.BOTH.get_target_values("gfx90a") returns
            ["gfx90a:xnack-", "gfx90a:xnack+"].
        """
        ret_arr = [base_target]
        if self is XnackMode.MINUS:
            ret_arr = [f"{base_target}:xnack-"]
        elif self is XnackMode.PLUS:
            ret_arr = [f"{base_target}:xnack+"]
        elif self is XnackMode.BOTH:
            ret_arr = [
                f"{base_target}:xnack-",
                f"{base_target}:xnack+",
            ]
        return ret_arr

    def get_next_mode(self):
        """Return the next mode in the wizard's Space-key cycle.

        Example:
            XnackMode.PLUS.get_next_mode() returns XnackMode.BOTH.
        """
        mode_order = [
            XnackMode.PLAIN,
            XnackMode.MINUS,
            XnackMode.PLUS,
            XnackMode.BOTH,
        ]
        mode_index = mode_order.index(self)
        ret = mode_order[(mode_index + 1) % len(mode_order)]
        return ret


class SanitizerMode(Enum):
    """Supported TheRock sanitizer build modes."""

    NONE = "NONE"
    HOST_ASAN = "HOST_ASAN"
    ASAN = "ASAN"

    def get_display_name(self, device_targets=None):
        """Return the human-readable sanitizer mode name.

        Example:
            SanitizerMode.HOST_ASAN.get_display_name() returns
            "Host ASAN".
        """
        display_names = {
            SanitizerMode.NONE: "Normal build",
            SanitizerMode.HOST_ASAN: "Host ASAN",
            SanitizerMode.ASAN: "Host and device ASAN",
        }
        ret = display_names[self]
        if self is SanitizerMode.ASAN and device_targets is not None:
            if device_targets:
                target_names = ", ".join(device_targets)
                ret = (
                    "Host ASAN for all selected GPUs and device "
                    "ASAN for "
                    + target_names
                )
            else:
                ret = (
                    "Host ASAN for all selected GPUs; no selected "
                    "GPU supports device ASAN"
                )
        return ret


def get_xnack_mode_from_targets(base_target, target_values):
    """Return one XNACK mode represented by configured target values.

    Example:
        For gfx90a with both qualified values, this returns
        XnackMode.BOTH.
    """
    unique_values = frozenset(target_values)
    mode_by_values = {
        frozenset({base_target}): XnackMode.PLAIN,
        frozenset(
            {f"{base_target}:xnack-"}
        ): XnackMode.MINUS,
        frozenset(
            {f"{base_target}:xnack+"}
        ): XnackMode.PLUS,
        frozenset(
            {
                f"{base_target}:xnack-",
                f"{base_target}:xnack+",
            }
        ): XnackMode.BOTH,
    }
    ret = mode_by_values.get(unique_values)
    if ret is None:
        raise ValueError(
            "Conflicting XNACK target forms for "
            + base_target
        )
    return ret


def normalize_gpu_targets(gpu_targets, sanitizer):
    """Validate GPU target forms and apply full-ASAN XNACK+ rules.

    Example:
        normalize_gpu_targets(["gfx942"], "ASAN") returns
        ["gfx942:xnack+"].
    """
    ret_arr = []
    values_by_base = {}
    asan_target_found = False
    for target in gpu_targets:
        base_target = target.split(":", 1)[0]
        if ":xnack" in target:
            if base_target not in XNACK_CAPABLE_TARGETS:
                raise ValueError(
                    "XNACK mode is not supported for "
                    + base_target
                )
        if base_target in XNACK_CAPABLE_TARGETS:
            if base_target in ASAN_DEVICE_TARGETS:
                asan_target_found = True
            target_values = values_by_base.get(base_target, [])
            target_values.append(target)
            values_by_base[base_target] = target_values

    sanitizer_mode = SanitizerMode(sanitizer or "NONE")
    processed_targets = set()
    for target in gpu_targets:
        base_target = target.split(":", 1)[0]
        if base_target in XNACK_CAPABLE_TARGETS:
            if base_target not in processed_targets:
                mode = get_xnack_mode_from_targets(
                    base_target,
                    values_by_base[base_target],
                )
                if (
                    sanitizer_mode is SanitizerMode.ASAN
                    and base_target in ASAN_DEVICE_TARGETS
                ):
                    if mode in [XnackMode.MINUS, XnackMode.BOTH]:
                        raise ValueError(
                            "Device ASAN requires Plain or XNACK+ for "
                            + base_target
                        )
                    mode = XnackMode.PLUS
                ret_arr.extend(
                    mode.get_target_values(base_target)
                )
                processed_targets.add(base_target)
        elif target not in processed_targets:
            ret_arr.append(target)
            processed_targets.add(target)

    if (
        sanitizer_mode is SanitizerMode.ASAN
        and not asan_target_found
    ):
        raise ValueError(
            "Device ASAN requires gfx906, gfx90a, gfx942, "
            "or gfx950"
        )
    return ret_arr
