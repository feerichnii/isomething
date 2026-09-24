"""Project-specific exception hierarchy."""


class CarrierLabError(Exception):
    """Base class for all CarrierBundleLab errors."""


class DeviceError(CarrierLabError):
    """Device discovery or session failed."""


class DeviceConnectionError(DeviceError):
    """Device discovery or USB/lockdown connection failed."""


class DeviceNotFoundError(DeviceError):
    """The requested device is not connected."""


class MultipleDevicesError(DeviceError):
    """More than one device is connected and no UDID was selected."""


class CompatibilityError(CarrierLabError):
    """CarrierLab asset compatibility failed."""


class UnsupportedDeviceError(CompatibilityError):
    """The connected device is unsupported."""


class UnsupportedIOSVersionError(CompatibilityError):
    """The connected iOS version is unsupported."""


class UnsupportedIOSBuildError(CompatibilityError):
    """The connected iOS build has no exact CarrierLab mapping."""


class BundleCompatibilityError(CompatibilityError):
    """No compatible CarrierLab asset could be selected safely."""


class TransportError(CarrierLabError):
    """Transport backend failed."""


class TransportUnavailableError(TransportError):
    """The configured transport backend is unavailable."""


class TransportProbeError(TransportError):
    """Transport probe failed."""


class TransportVerificationError(TransportError):
    """Transport verification failed."""


class BackupError(CarrierLabError):
    """Backup creation or verification failed."""


class BackupVerificationError(BackupError):
    """Backup manifest verification failed."""


class MigrationError(CarrierLabError):
    """Carrier tree migration planning failed."""


class InstallError(CarrierLabError):
    """Carrier tree install failed."""


class ReadbackVerificationError(CarrierLabError):
    """Installed tree readback does not match expectations."""


class RescanError(CarrierLabError):
    """Carrier configuration re-evaluation trigger failed."""


class BindingError(CarrierLabError):
    """Carrier binding verification failed."""


class BindingTimeoutError(BindingError):
    """Timed out waiting for CommCenter binding."""


class BindingVerificationError(BindingError):
    """CommCenter did not confirm the expected binding."""


class RecoveryError(CarrierLabError):
    """Rollback or transaction recovery failed."""


class RestoreVerificationError(RecoveryError):
    """Restored tree does not match the original manifest."""


class TransactionError(CarrierLabError):
    """Transaction journal or lock failed."""


class InvalidTransactionTransition(TransactionError):
    """The requested transaction state transition is not allowed."""


class TransactionLockedError(TransactionError):
    """Another carrier transaction is already active for this device."""
