// Which run a page waiting on a run it started should show (E174): the newest run only once it is newer than the newest
// run there was when this one was started — never the run that was already there.
export function arrivedRun(latest: string | null, newestAtStart: string | null, waiting: boolean): string | null {
  return waiting && latest !== null && latest !== newestAtStart ? latest : null
}
