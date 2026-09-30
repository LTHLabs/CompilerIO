// Verified Library Catalog (M2.2)
//
// Each entry maps a detected #include header to a PlatformIO Registry
// dependency that has actually been build-verified end to end (Web App ->
// Local Agent -> dependency preparation -> offline compile -> firmware).
//
// Do not add an entry here without that verification. An unverified guess
// belongs nowhere in this file — see docs/PROJECT_STATE.md for the backlog
// of headers still needing verification. `platformioName` must always be an
// exact, owner-qualified Registry spec (`owner/name@version`), matching what
// `local-agent/app/dependency_validator.py` requires.

const LIBRARY_CATALOG = {
  'DHT.h': {
    name: 'DHT sensor library',
    platformioName: 'adafruit/DHT sensor library@1.4.4',
    verifiedAt: '2026-09-27',
    verifiedBy: 'M2.1.2 Gate 1 + Gate 4 (Eksperiment/validation/m2.1.2-validation-2026-09-27.md)',
  },
};

export { LIBRARY_CATALOG };
