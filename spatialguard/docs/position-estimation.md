# Calibration-free position estimation

**The idea.** Pathlight places people on a floor plan from ordinary Ring cameras, with no per-camera calibration: no checkerboards, no clicking reference points, no measuring. The owner does what they would do anyway. They drop each camera on their floor plan where it hangs, aim it, and say what it is. Pathlight then turns each detected person into an **estimated** floor position and shows the uncertainty honestly. It does not present a false-precision dot.

Calibration is the step that keeps camera analytics out of small shops: it takes an installer, a visit and equipment. Pathlight replaces it with weak geometric priors the owner already knows, and is open about what that costs.

## How it works

Code: `spatialguard/services/api/spatialguard_api/person_tracking.py`, `tracks.py` and `heatmap.py` (`project_foot`).

1. **Detect the person and take the foot point.** YOLO11n (ONNX, run through OpenCV 5) finds people in the Ring recording. The bottom-centre of each box, where the feet meet the floor, is the person's image position. Short dropouts are filled, and the foot point is median-filtered and then smoothed, so detector jitter doesn't become fake movement.
2. **Bearing from the horizontal position.** The owner sets the camera's heading on the map. The horizontal field of view (FOV, 110° by default from Ring's published lens spec) maps image x linearly to an angle: `bearing = heading + (0.5 − x) · FOV`. One pixel column is the same angle across the frame, which is the equidistant model typical of wide-angle and fisheye lenses.
3. **Distance from the vertical position.** For a camera mounted above a flat floor, a foot point lower in the image is nearer, and one higher (toward the horizon) is farther. Pathlight maps the foot point's height to a distance between a near limit and the owner-set range, along a curve that rises faster toward the far edge, as ground-plane geometry does. Foot points in the top 35% of the frame are clamped to the far limit, because near the horizon distance becomes unreliable.
4. **Show uncertainty and label everything.**
   - Every derived position is stored and displayed as an *estimate*.
   - The heatmap draws each position as a Gaussian footprint rather than a point.
   - Positions are anonymous floor points; there are no faces and no identity.
   - Events that haven't been analyzed yet are drawn as one estimated dot and counted separately, so the map says how much of it is estimated.

## What the research says

| Pathlight step | Supporting work | What it shows, and its limits |
|---|---|---|
| Foot point = ground position (1) | Hoiem, Efros & Hebert, *Putting Objects in Perspective*, IJCV 2008 [1] | Objects rest on the ground plane, and an object's bottom position relative to the horizon encodes its depth. Viewpoint is estimated probabilistically, not calibrated. They note the approximation weakens for strongly tilted, wide-angle cameras. |
| Foot point = ground position (1) | Rezaei & Azarmi, *DeepSOCIAL*, Applied Sciences 2020 [2] | Uses "the midpoint of the bottom edge of the detected bounding boxes" (the shoes) as each person's ground point from monocular CCTV. Their bird's-eye mapping still uses camera height and optics, so we cite them only for the foot-point convention. |
| Useful positions from an uncalibrated camera (2–4) | Aghaei et al., *Single Image Human Proxemics Estimation for Visual Social Distancing*, WACV 2021 [3] | **The closest precedent.** Works "given a single uncalibrated image in unconstrained scenarios", with "a semi-automatic solution to approximate the homography matrix between the scene ground and image plane". A few hand-tuned ratios stand in for camera tilt and height, much as Pathlight's owner-set heading and range do. They evaluate distance-violation detection, not metric position error. |
| Ground-plane measurement without internal calibration (3–4) | Criminisi, Reid & Zisserman, *Single View Metrology*, IJCV 2000 [4] | Affine measurements on a reference plane from one image, without the camera's internal calibration. Uncertainty is propagated to each measurement. Metric scale needs a reference length, which the owner's floor plan supplies. |
| Linear angle per pixel (2) | Kannala & Brandt, *A Generic Camera Model and Calibration Method for Conventional, Wide-Angle, and Fish-Eye Lenses*, IEEE TPAMI 2006 [5] | Fisheye lenses are usually designed to an ideal projection, "perhaps the most common" being the equidistance projection r = f·θ. That is the linear bearing model. Real lenses deviate from it; that deviation is what the paper calibrates. |
| Report uncertainty, not a point (4) | Bertoni, Kreiss & Alahi, *MonoLoco*, ICCV 2019 [6] | Single-camera pedestrian localization is ill-posed, so they predict confidence intervals (a Laplace-based loss). The error from ambiguity grows with distance. MonoLoco itself uses camera intrinsics. |
| Future: calibrate from the visitors themselves | Krahnstoever & Mendonça, *Bayesian Autocalibration for Surveillance*, ICCV 2005 [7]; Lv, Zhao & Nevatia, *Camera Calibration from Video of a Walking Human*, IEEE TPAMI 2006 [8] | Observations of people walking are enough to recover a camera's parameters after installation, with a posterior over the result. Pathlight already collects exactly these foot and head observations. |
| Future: infer the lens and tilt from one frame | Veicht et al., *GeoCalib*, ECCV 2024 [9]; Jin et al., *Perspective Fields for Single Image Camera Calibration*, CVPR 2023 [10] | Single-image estimation of focal length, roll and pitch, with uncertainty, so calibration can be inferred rather than measured. Not yet validated on night or infrared doorbell frames. |

**In one paragraph:** taking the bottom-centre of a person box as the ground position is established practice in single-camera people mapping [1–3]. Single-view geometry shows that positions on the ground plane are recoverable without full calibration [1, 4], and that a few rough priors standing in for tilt and height already give useful distance judgements from an uncalibrated image [3]. The equidistant lens model supports a linear angle per pixel for wide-angle cameras [5]. Single-camera localization should come with uncertainty that grows with distance [4, 6]. The same people Pathlight already detects could later be used to calibrate each camera automatically [7–10].

## Limits we state plainly

- **Bias, not just noise.** A wrong heading, mounting height or range moves every position from that camera the same way. A wider footprint shows uncertainty; it doesn't remove bias. Calibrated systems avoid this.
- **Wide angle and steep tilt** are where ground-plane approximations are weakest [1]. Ring doorbells are both.
- **A constant footprint.** The heatmap currently uses one footprint width for walked paths. The literature [6] suggests widening it with distance from the camera; that is a planned improvement.
- **Directional, not survey-grade.** Use Pathlight for "where do people go and wait", not for distances accurate to the centimetre. Validation on real visits: in a 20-pass test with the three physical cameras, Pathlight counted 19 of 20 walk-bys, with a mean floor-position error of 0.42 m (median 0.35 m, 90th percentile 0.78 m). See [Accuracy test results](../../README.md#pathlight-accuracy-test-results).

## References

1. D. Hoiem, A. A. Efros, M. Hebert. "Putting Objects in Perspective." *International Journal of Computer Vision* 80(1):3–15, 2008. https://doi.org/10.1007/s11263-008-0137-5 (conference version: CVPR 2006, https://doi.org/10.1109/CVPR.2006.232)
2. M. Rezaei, M. Azarmi. "DeepSOCIAL: Social Distancing Monitoring and Infection Risk Assessment in COVID-19 Pandemic." *Applied Sciences* 10(21):7514, 2020. https://doi.org/10.3390/app10217514
3. M. Aghaei, M. Bustreo, Y. Wang, G. Bailo, P. Morerio, A. Del Bue. "Single Image Human Proxemics Estimation for Visual Social Distancing." *WACV* 2021, pp. 2785–2795. https://openaccess.thecvf.com/content/WACV2021/html/Aghaei_Single_Image_Human_Proxemics_Estimation_for_Visual_Social_Distancing_WACV_2021_paper.html
4. A. Criminisi, I. Reid, A. Zisserman. "Single View Metrology." *International Journal of Computer Vision* 40(2):123–148, 2000. https://doi.org/10.1023/A:1026598000963
5. J. Kannala, S. S. Brandt. "A Generic Camera Model and Calibration Method for Conventional, Wide-Angle, and Fish-Eye Lenses." *IEEE TPAMI* 28(8):1335–1340, 2006. https://doi.org/10.1109/TPAMI.2006.153
6. L. Bertoni, S. Kreiss, A. Alahi. "MonoLoco: Monocular 3D Pedestrian Localization and Uncertainty Estimation." *ICCV* 2019, pp. 6861–6871. https://openaccess.thecvf.com/content_ICCV_2019/html/Bertoni_MonoLoco_Monocular_3D_Pedestrian_Localization_and_Uncertainty_Estimation_ICCV_2019_paper.html
7. N. Krahnstoever, P. R. S. Mendonça. "Bayesian Autocalibration for Surveillance." *ICCV* 2005, pp. 1858–1865. https://doi.org/10.1109/ICCV.2005.44
8. F. Lv, T. Zhao, R. Nevatia. "Camera Calibration from Video of a Walking Human." *IEEE TPAMI* 28(9):1513–1518, 2006. https://dblp.uni-trier.de/pid/62/6776-1
9. A. Veicht, P.-E. Sarlin, P. Lindenberger, M. Pollefeys. "GeoCalib: Learning Single-image Calibration with Geometric Optimization." *ECCV* 2024. https://doi.org/10.1007/978-3-031-73661-2_1
10. L. Jin, J. Zhang, Y. Hold-Geoffroy, O. Wang, K. Blackburn-Matzen, M. Sticha, D. F. Fouhey. "Perspective Fields for Single Image Camera Calibration." *CVPR* 2023, pp. 17307–17316. https://openaccess.thecvf.com/content/CVPR2023/html/Jin_Perspective_Fields_for_Single_Image_Camera_Calibration_CVPR_2023_paper.html
