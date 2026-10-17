// Years on the intake page: the financial years a file can be for (the last four completed, plus any already on file),
// and a projection year in the reader's words.
export const lastYear = new Date().getFullYear() - 1
export const periodsWith = (onFile: string[]) => [...new Set([0, 1, 2, 3].map(i => `FY${lastYear - i}`).concat(onFile))].sort().reverse()
export const yearLabel = (h: string) => h === 'current' ? 'Today' : h
