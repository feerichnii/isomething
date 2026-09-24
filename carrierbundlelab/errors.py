"""Project-specific exception hierarchy."""


class CarrierLabError(Exception):
    """Base class for all CarrierBundleLab errors."""


class DeviceConnectionError(CarrierLabError):
    """Device discovery or USB/lockdown connection failed."""


class UnsupportedDeviceError(CarrierLabError):
    """The connected device is unsupported."""


class UnsupportedIOSVersionError(CarrierLabError):
    """The connected iOS version is unsupported."""


class BundleCompatibilityError(CarrierLabError):
    """No compatible CarrierLab asset could be selected safely."""


class TransportUnavailableError(CarrierLabError):
    """The configured transport backend is unavailable."""


class TransportVerificationError(CarrierLabError):
    """Transport verification failed."""


class BackupError(CarrierLabError):
    """Backup creation or verification failed."""


class MigrationError(CarrierLabError):
    """Carrier tree migration planning failed."""


class InstallError(CarrierLabError):
    """Carrier tree install failed."""


class ReadbackVerificationError(CarrierLabError):
    """Installed tree readback does not match expectations."""


class RescanError(CarrierLabError):
    """Carrier configuration re-evaluation trigger failed."""


class BindingVerificationError(CarrierLabError):
    """CommCenter did not confirm the expected binding."""


class RecoveryError(CarrierLabError):
    """Rollback or transaction recovery failed."""
