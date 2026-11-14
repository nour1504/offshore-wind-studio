/**
 * The colour of a level by its place in the column (0 at the ground, 1 at the top), the same in
 * the profile, in the levels in 3D and on their curtain; orange where a rotor crosses. The colours
 * themselves are in motion.css (--ows-stack-*).
 */
export const levelColour = (share: number, rotor = false) =>
  rotor ? "var(--ows-stack-rotor)" : `color-mix(in srgb, var(--ows-stack-low) ${Math.round((1 - share) * 100)}%, var(--ows-stack-high))`;
