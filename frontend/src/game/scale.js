// Physical scaling: the battlefield is 60" x 44" (standard AoS matched
// play). All game logic works in inches; only rendering converts to px.
export const BOARD_W_IN = 60;
export const BOARD_H_IN = 44;
export const PX_PER_INCH = 16;
export const ZONE_DEPTH_IN = 12; // deployment zone depth from each long edge

export const inToPx = (inches) => inches * PX_PER_INCH;
export const pxToIn = (px) => px / PX_PER_INCH;

export const CANVAS_W = inToPx(BOARD_W_IN);
export const CANVAS_H = inToPx(BOARD_H_IN);
