from grid.scientific_surfaces import fit_polynomial_surface,PolynomialSurfaceTracker

def test_quadratic_surface_recovers_known_chart():
    pts=[]
    for i in range(-5,6):
        for j in range(-5,6):
            x=i/3;y=j/3;z=1+2*x-3*y+.5*x*x+.25*x*y-.75*y*y
            pts.append((x,y,z))
    m=fit_polynomial_surface(pts,2)
    assert m and m["rmse"]<1e-5

def test_cubic_surface_improves_on_cubic_structure():
    pts=[]
    for i in range(-6,7):
        for j in range(-6,7):
            x=i/4;y=j/4;z=x*x*x-.5*x*y*y+2*y
            pts.append((x,y,z))
    q=fit_polynomial_surface(pts,2);c=fit_polynomial_surface(pts,3)
    assert q and c and c["rmse"]<q["rmse"]*.2

def test_tracker_scores_before_learning_current_point():
    t=PolynomialSurfaceTracker(2,window=128)
    for i in range(30):
        x=i/10;y=(i%5)/10;z=x+y
        t.score_then_update((x,y,z))
    out=t.score_then_update((4,4,20))
    assert out["ready"] and abs(out["residual_z"])>3
