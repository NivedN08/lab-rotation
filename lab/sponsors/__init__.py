"""lab.sponsors: one client per sponsor, each with a recorded fallback.

- band.BandRoom: the panel's BAND room (local room when BAND is down)
- telem.Librarian: Telem AI search, fetch and case of the day (cached results)
- runware.Runware: voices, portraits, Riley on an open model (browser / claude -p)
- glasser.Glasser: real retail numbers for the task generator (recorded set)
- teamily.Teamily: practice summary after a rotation (stub, saved locally)

Every call reports a calls.SponsorCall; `.event_data()` is the `sponsor.call` event data.
"""
