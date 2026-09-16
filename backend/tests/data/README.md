# Test fixtures

`synthetic_environment_grid.csv` is **NOT a dataset**. It is four hand-written
grid nodes at two times, with values chosen so interpolation is checkable by
eye (a midpoint must equal the mean of its neighbours). It lives here, never in
`backend/data/environment/`, so it cannot be mistaken for real environmental
data or be picked up by the running app.
