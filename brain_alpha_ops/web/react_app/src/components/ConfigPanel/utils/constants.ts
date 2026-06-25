/** Default configuration constants and patterns for ConfigPanel. */

export const MAX_CONFIG_TEXT_LENGTH = 128;
export const CONFIG_TEXT_PATTERN = /^[A-Za-z0-9_.:-]*$/;
export const DEFAULT_REGION_OPTIONS = ['USA', 'CHN', 'EUR', 'GLB'];
export const DEFAULT_UNIVERSE_OPTIONS = ['TOP3000', 'TOP1000', 'TOP500'];
export const DEFAULT_DELAY_OPTIONS = ['0', '1'];
export const DEFAULT_NEUTRALIZATION_OPTIONS = [
  'SUBINDUSTRY',
  'INDUSTRY',
  'SECTOR',
  'MARKET',
  'NONE',
];
export const DEFAULT_INSTRUMENT_TYPE_OPTIONS = ['EQUITY'];
export const DEFAULT_PASTEURIZATION_OPTIONS = ['ON', 'OFF'];
export const DEFAULT_UNIT_HANDLING_OPTIONS = ['VERIFY', 'RAW', 'NONE'];
export const DEFAULT_NAN_HANDLING_OPTIONS = ['ON', 'OFF'];
export const DEFAULT_LANGUAGE_OPTIONS = ['FASTEXPR'];
export const DEFAULT_ALPHA_TYPE_OPTIONS = ['REGULAR', 'POWER_POOL', 'ATOM', 'PYRAMID'];
