// Size-comparison element for the At a Glance card, following the same
// established pattern All About Birds itself uses on its own
// "Relative Size" section: silhouettes above a line of discrete points,
// one point highlighted, and a single descriptive caption below.
//
// The silhouettes are artwork, not hand-drawn — four are
// CC0-licensed SVGs from SVG Repo (svgrepo.com), verified directly;
// Robin is a robin silhouette (provided directly, confirmed CC0)
// traced to a vector path with potrace, replacing an earlier version of
// this position that used mislabeled pigeon artwork as a stand-in
// before a robin silhouette was available — see BIRD_SVGS.robin's
// own comment for that trace. Every SVG Repo path below was copied
// verbatim from the downloaded source, license confirmed as CC0 (public
// domain, no attribution required) on each icon's page before use:
// Hummingbird — svgrepo.com/svg/3466/hummingbird
// Sparrow — svgrepo.com/svg/21443/sparrow
// Raven — svgrepo.com/svg/123268/raven (used for "Crow")
// Eagle — svgrepo.com/svg/231/eagle (labeled "Hawk" —
// same artwork, more relatable name for a backyard-bird
// context)
//
// The reference points themselves (which cm value maps to which bird)
// are a standardized scale Chirp defines itself, not scraped from AAB's
// own separate internal size-bucket system.
const BIRD_SVGS = {
  hummingbird: {
    viewBox: '0 0 379.777 379.777',
    path: 'M366.314,97.749c-0.129-1.144-1.544-1.144-2.389-1.144c-6.758,0-37.499,4.942-62.82,13.081c-1.638,0.527-2.923,0.783-3.928,0.783c-1.961,0-2.722-0.928-4.254-3.029c-1.848-2.533-4.379-6.001-11.174-8.914c-2.804-1.202-6.057-1.812-9.667-1.812c-14.221,0-32.199,9.312-42.749,22.142c-0.066,0.08-0.103,0.096-0.107,0.096c-0.913,0-4.089-3.564-9.577-17.062c-4.013-9.87-8.136-22.368-10.504-31.842c-3.553-14.212-13.878-34.195-20.71-47.417c-2.915-5.642-5.218-10.098-5.797-11.836c-0.447-1.339-1.15-2.019-2.091-2.019c-0.604,0-1.184,0.3-1.773,0.917c-6.658,6.983-20.269,65.253-19.417,83.132c0.699,14.682,12.291,24.61,17.861,29.381c0.659,0.564,1.363,1.167,1.911,1.67c-2.964-1.06-9.171-6.137-17.406-12.873c-11.881-9.718-29.836-24.403-54.152-40.453c-34.064-22.484-55.885-44.77-68.922-58.084C29.964,3.599,26.338,0,23.791,0c-0.605,0-1.707,0.227-2.278,1.75c-2.924,7.798,0.754,88.419,37.074,132.002c20.279,24.335,46.136,36.829,63.246,45.097c9.859,4.764,17.647,8.527,18.851,12.058c0.273,0.803,0.203,1.573-0.223,2.425c-1.619,3.238-4.439,7.193-8.011,12.202c-9.829,13.783-24.682,34.613-35.555,69.335c-4.886,15.601-55.963,70.253-69.247,83.537c-0.648,0.648-15.847,15.917-14.06,20.229c0.142,0.344,0.613,1.143,1.908,1.143c3.176,0,11.554-5.442,24.902-16.195c17.47-14.073,29.399-25.848,38.11-34.452c8.477-8.374,13.784-13.596,17.427-14.161c-0.333,1.784-1.385,6.367-4.576,17.926c-0.077,0.279-0.238,0.938,0.127,1.418l0.355,0.576h0.495c0.001,0,0.002,0,0.003,0c0.773,0,1.172-0.618,4.53-4.786c10.244-12.714,41.417-51.561,84.722-60.067c25.376-4.985,56.886-28.519,68.008-63.854c16.822-53.439,30.902-87.056,105.176-104.081C366.502,99.413,366.428,98.751,366.314,97.749z',
  },
  sparrow: {
    viewBox: '0 0 338.234 338.234',
    path: 'M289.907,70.398c20.551-11.21,24.203-13.379,24.125-15.549c-0.018-0.487-0.257-1.166-1.296-1.639c-2.043-0.93-4.01-1.481-5.913-2.014c-3.904-1.094-7.276-2.039-10.483-5.884c-1.515-1.816-3.19-5.116-5.13-8.937c-6.14-12.093-15.419-30.368-35.404-35.173C252.483,0.405,249.124,0,245.819,0c-12.257,0-23.432,5.395-32.315,15.601c-9.916,11.393-16.38,27.889-19.213,49.032c-3.556,26.537-42.166,76.738-65.234,106.733c-7.831,10.182-14.017,18.224-16.415,22.217c-8.857,14.743-25.584,34.13-39.025,49.708c-15.501,17.967-23.576,27.509-23.246,31.08c0.065,0.704,0.411,1.118,0.69,1.341c0.385,0.308,0.888,0.464,1.496,0.464c4.94,0,21.448-12.124,36.73-24.104c-10.402,10.931-23.707,25.778-36.707,40.287c-4.024,4.491-7.98,8.905-11.752,13.093c-11.723,13.017-18.132,24.048-16.326,28.104c0.458,1.028,1.393,1.595,2.632,1.595c3.332,0,8.409-4.028,12.082-7.408c6.64-6.111,10.544-8.385,12.035-8.495c-0.004,0.455-0.375,1.779-2.126,4.342c-3.955,5.787-5.545,10.701-4.255,13.145c0.51,0.967,1.432,1.5,2.595,1.5c2.449,0,5.959-2.402,9.885-6.758c10.59-11.749,46.677-45.226,64.02-61.312c4.808-4.46,8.038-7.463,8.834-8.244c0.229-0.081,1.017-0.245,3.72-0.245c2.097,0,4.952,0.053,8.258,0.149c5.062,0.148,11.361,0.27,18.48,0.27c0.003,0,0.003,0,0.006,0c3.367,0,6.649-0.047,9.865-0.133c0.149,3.07-0.095,6.791-1.18,7.6c-0.1,0.074-0.245,0.166-0.434,0.287c-1.243,0.796-4.155,2.662-8.612,7.718c-1.786,2.026-3.755,4.793-2.997,6.472c0.273,0.604,0.855,0.964,1.558,0.964h0c0.848,0,1.87-0.523,2.875-1.472c7.321-6.906,16.732-10.867,25.82-10.867c1.375,0,2.75,0.093,4.088,0.276c6.108,0.836,7.203,1.308,9.19,2.164c0.909,0.392,2.04,0.878,3.886,1.498c0.829,0.277,1.574-0.159,1.718-0.927c0.345-1.843-3.449-6.933-6.55-8.136c-2.834-1.1-6.013-1.657-9.446-1.657c-3.584,0-6.753,0.585-9.067,1.013c-1.058,0.196-1.987,0.367-2.558,0.4c-0.083-1.309-0.042-3.839,0.009-5.658c13.413-0.703,25.416-2.22,36.051-4.577c7.512,4.517,14.442,8.799,15.146,9.566c0.333,0.453-0.217,2.537-0.619,4.059c-0.499,1.889-1.063,4.029-1.198,6.267c-0.182,3.016,0.872,5.597,1.928,6.718c0.473,0.502,0.972,0.756,1.484,0.756c0.355,0,1.521-0.152,1.639-2.114c0.173-2.882,4.284-12.004,7.5-14.99c5.245-4.868,9.782-5.318,16.604-5.062c5.505,0.206,9.673,1.614,11.676,2.291c0.863,0.292,1.257,0.425,1.594,0.425h0c0.402,0,0.756-0.198,0.946-0.53l0.269-0.593l-0.292-0.5c-0.685-1.175-4.476-5.904-10.507-7.565c-3.481-0.959-6.728-1.445-9.649-1.445c-5.626,0-9.029,1.729-11.514,2.991c-1.368,0.696-2.371,1.23-3.168,1.077c-1.156-0.226-4.804-2.165-9.259-4.731c13.639-4.382,24.52-10.496,32.798-18.398c41.914-40.009,39.871-88.999,30.776-123.104c-2.477-9.288-5.682-16.022-8.021-20.938C278.059,80.821,276.563,77.677,289.907,70.398zM158.867,284L158.867,284L158.867,284L158.867,284z',
  },
  robin: {
    // robin silhouette, provided directly (confirmed CC0) as a
    // raster PNG — traced to a vector path with potrace (thresholded to
    // pure black/white against a white background first, since the
    // source had transparency; a first attempt without properly
    // flattening that transparency traced as one solid rectangle
    // instead of the bird shape, caught by rendering and viewing
    // the result before using it). potrace's own output includes a
    // group-level transform (flips Y, since raster Y increases downward
    // while potrace's path coordinates are in the original bitmap's
    // coordinate space) — kept as-is and applied as a wrapping <g>
    // rather than hand-recomputing 3600+ characters of coordinates,
    // which would risk introducing errors.
    groupTransform: 'translate(0,1255) scale(0.1,-0.1)',
    viewBox: '0 0 1280 1255',
    path: 'M10090 12543 c-201 -15 -476 -57 -682 -103 -267 -61 -548 -156 -548 -186 0 -14 81 -34 135 -34 56 0 40 -14 -37 -34 -133 -34 -432 -127 -445 -138 -18 -15 -11 -22 74 -79 41 -28 73 -52 71 -54 -2 -1 -43 -26 -93 -55 -384 -226 -711 -498 -997 -830 -128 -149 -308 -329 -495 -492 -294 -258 -808 -675 -1148 -933 -1668 -1263 -2560 -1984 -2841 -2297 -66 -73 -80 -108 -54 -141 l19 -24 -65 -64 c-36 -35 -104 -108 -152 -162 -68 -77 -157 -155 -405 -354 -1291 -1035 -2143 -1824 -2359 -2186 -51 -85 -67 -130 -68 -188 0 -41 4 -51 34 -77 26 -22 49 -32 89 -37 270 -34 783 252 1465 815 90 74 173 141 184 149 11 8 -23 -39 -75 -104 -154 -192 -236 -344 -237 -437 0 -39 5 -51 32 -78 80 -81 161 -24 878 620 443 398 857 749 883 750 5 0 -14 -26 -41 -57 -241 -280 -306 -500 -168 -567 36 -18 48 -19 126 -9 91 12 253 56 360 98 39 16 101 29 155 35 82 8 185 37 300 84 22 10 143 67 268 129 163 80 232 109 241 102 8 -6 112 -89 232 -186 290 -234 534 -417 614 -461 134 -75 310 -142 619 -234 353 -105 364 -116 740 -664 192 -282 244 -350 257 -337 7 6 -29 221 -44 267 -18 53 43 -56 251 -455 660 -1263 1076 -2080 1064 -2092 -4 -3 -112 9 -239 27 -448 65 -598 39 -673 -115 -26 -52 -27 -62 -22 -148 4 -69 15 -121 43 -207 l38 -115 12 67 c19 98 50 161 103 211 159 149 420 155 765 16 54 -21 207 -98 340 -171 253 -138 646 -337 756 -383 36 -15 130 -50 210 -77 262 -89 351 -166 405 -351 14 -49 36 -109 50 -135 l24 -47 1 72 c0 40 7 115 16 165 20 113 14 219 -14 275 -27 53 -102 120 -165 147 -29 13 -101 38 -161 56 -60 18 -159 52 -220 75 -138 52 -597 247 -593 251 2 2 84 -19 182 -47 282 -78 512 -136 615 -154 176 -31 262 -76 343 -183 67 -89 87 -126 127 -240 26 -72 39 -100 43 -86 17 58 29 184 25 266 -3 83 -8 103 -41 171 -45 96 -127 181 -214 226 -76 38 -115 47 -268 60 -66 6 -176 21 -245 32 -132 22 -471 103 -499 119 -20 12 194 12 584 1 315 -10 339 -14 451 -92 68 -47 196 -170 224 -214 10 -17 31 -69 46 -115 34 -109 37 -114 46 -60 12 79 8 214 -7 273 -43 165 -170 306 -349 387 -138 63 -282 75 -468 41 -57 -11 -129 -22 -160 -26 l-58 -6 0 53 c0 155 162 309 357 340 136 21 385 -9 558 -67 28 -9 199 -76 380 -147 406 -161 694 -257 887 -297 82 -17 172 -39 201 -49 128 -45 212 -127 292 -283 31 -60 58 -109 61 -109 3 0 2 82 -1 183 -8 211 -19 261 -76 322 -58 62 -134 92 -356 137 -212 43 -830 214 -783 217 8 0 101 -12 205 -28 211 -33 471 -65 643 -79 89 -8 125 -16 167 -37 109 -53 226 -184 299 -335 l41 -85 3 134 c4 208 -25 290 -144 408 -39 38 -88 74 -131 95 l-68 33 -295 6 c-276 6 -423 18 -650 53 -84 12 -84 13 -40 19 144 21 738 80 810 80 63 1 100 -5 144 -21 87 -32 197 -105 280 -185 61 -61 78 -85 106 -152 18 -44 37 -84 42 -89 13 -15 9 131 -6 215 -20 113 -58 181 -152 276 -138 140 -294 199 -509 190 -92 -3 -129 -10 -222 -40 -181 -59 -215 -62 -558 -61 -170 1 -339 6 -375 10 l-65 9 -617 970 c-340 534 -631 995 -647 1025 -16 31 -37 87 -45 125 -26 117 -56 296 -56 335 l0 36 143 33 c585 136 1059 393 1471 799 347 342 608 737 789 1197 87 222 93 247 167 760 58 400 58 393 10 1365 -36 730 -45 1101 -32 1381 13 287 33 407 87 532 130 304 431 646 778 886 166 114 267 232 382 444 45 84 47 89 29 102 -72 53 -278 47 -614 -19 -283 -56 -355 -63 -455 -46 -70 12 -77 16 -110 56 -42 51 -214 201 -306 267 -147 105 -309 150 -599 167 -153 9 -507 11 -610 3z m-1674 -8279 c176 -256 237 -334 250 -321 4 4 1 44 -8 90 l-16 82 26 -33 c30 -38 438 -634 775 -1132 304 -448 607 -910 607 -926 0 -10 -68 -12 -297 -11 -254 2 -308 -1 -366 -15 -85 -22 -133 -47 -173 -90 -57 -60 -67 -91 -61 -192 4 -78 10 -106 46 -190 22 -55 41 -103 41 -107 0 -17 -300 18 -548 63 -144 26 -176 35 -187 52 -29 44 -1095 2277 -1114 2333 -25 75 -91 398 -98 483 -5 57 -2 68 17 93 13 16 32 32 44 37 12 4 195 11 406 15 212 4 387 9 389 11 2 2 26 4 51 4 l47 0 169 -246z',
  },
  crow: {
    // artwork is a raven silhouette
    viewBox: '0 0 360.416 360.416',
    path: 'M358.952,150.509c2.597-11.582,1.212-22.53-0.127-33.119c-1.144-9.042-2.223-17.581-0.591-25.51c3.869-18.796-8.128-39.427-19.013-55.301c-12.143-17.708-25.283-20.22-42.522-21.836c-0.932-0.087-1.884-0.132-2.829-0.132c-11.568,0-21.231,6.474-26.423,9.952c-1.347,0.902-2.739,1.835-3.147,1.917c-0.646,0.129-2.158,0.149-4.071,0.175c-5.138,0.068-13.736,0.183-23.974,2.376c-9.976,2.138-17.97,7.219-17.821,11.327c0.056,1.556,1.194,3.561,6.298,4.274c10.694,1.495,20.149,4.392,27.746,6.719c1.502,0.46,2.911,0.892,4.218,1.277c8.22,2.426,15.813,5.741,18.413,19.486c1.809,9.558-14.625,20.525-29.123,30.202c-6.014,4.013-11.693,7.804-16.268,11.521c-15.954,12.963-46.374,39.235-56.119,48.467c-9.237,8.751-86.918,62.013-107.799,72.199c-21.338,10.409-42.134,26.726-47.345,37.147c-1.168,2.336-1.418,3.816-0.812,4.797c0.265,0.428,0.812,0.938,1.915,0.938c1.313,0,3.111-0.757,4.662-1.491c0.002,0.188,0.037,0.381,0.119,0.578c0.463,1.119,1.955,1.262,3.203,1.262c3.411,0,10.521-1.401,19.192-3.771c-3.114,2.302-9.293,6.265-14.915,9.871C9.595,298.094-0.274,305.019,0.006,308.368c0.154,1.855,1.38,4.066,6.345,4.066c3.048,0,6.762-0.783,9.747-1.412c1.549-0.326,2.891-0.609,3.818-0.717c-0.338,0.709-1.205,1.928-1.82,2.794c-1.992,2.802-4.052,5.7-2.585,7.534c0.44,0.551,1.189,0.819,2.287,0.819c3.285,0,10.301-2.437,17.086-4.794c4.844-1.683,9.419-3.272,12.184-3.825c4.222-0.844,24.688-11.443,44.479-21.693c14.766-7.647,31.502-16.314,33.303-16.512c3.507,0,31.84-2.067,49.711-7.174c3.983-1.138,8.238-1.715,12.647-1.715c10.719,0,21.066,3.333,29.931,6.643c-0.055,2.158-0.109,4.802-0.165,8.048c-0.151,8.905-0.218,18.128-0.196,20.565c0.029,3.404,6.457,9.411,15.534,17.525c3.734,3.338,8.317,7.436,9.159,8.91c-1.521,0.946-3.853,0.974-6.745,1.009c-5.052,0.061-11.97,0.144-19.146,5.616c-4.179,3.187-6.942,7.744-7.569,9.963c-0.059,0.205-0.234,0.828,0.152,1.339c0.215,0.283,0.545,0.446,0.906,0.446c0.301,0,0.604-0.112,0.93-0.342l0.737-0.527c2.341-1.677,7.822-5.605,10.766-6.725c3.979-1.514,6.902-2.131,10.092-2.131c4.188,0,9.138,1.076,16.806,3.063c4.696,1.216,8.705,1.808,12.256,1.808c4.619,0,7.973-0.978,11.523-2.013c4.131-1.204,8.401-2.449,15.383-2.449c1.297,0,2.665,0.044,4.067,0.132c7.649,0.479,14.502,4.462,17.796,6.376c1.418,0.824,1.847,1.073,2.311,1.073l0.706-0.028l0.265-0.59c0.347-0.771-0.089-1.261-2.182-3.619c-3.516-3.959-6.806-6.381-9.986-7.947c1.944-0.378,3.739-0.896,5.584-1.434c4.131-1.204,8.401-2.449,15.382-2.449c1.297,0,2.665,0.044,4.067,0.132c7.649,0.479,14.503,4.462,17.796,6.375c1.419,0.825,1.848,1.073,2.312,1.073l0.706-0.028l0.265-0.59c0.347-0.771-0.089-1.261-2.182-3.619c-7.444-8.383-13.889-9.927-20.382-10.875c-2.55-0.371-4.478-1.228-4.688-2.082c-0.173-0.699,0.774-1.882,2.534-3.164c3.122-2.274,6.262-3.427,9.333-3.427c5.441,0,8.826,3.572,9.194,4.93c0.166,0.616,0.653,0.834,1.021,0.834c0.375,0,0.87-0.228,1.03-0.868c0.301-1.196-0.06-6.437-4.487-8.808c-2.211-1.185-5.633-1.837-9.636-1.837c-9.456,0-19.744,3.326-28.221,9.011c-1.689-0.342-3.622-0.526-5.722-0.526c-0.583,0-1.17,0.018-1.758,0.043c-7.241-5.788-19.983-19.26-20.717-23.842c-0.483-3.021-0.765-12.566-0.765-21.797c0-0.035,0-0.068,0-0.103c6-2.984,12.091-6.5,19.155-10.656C325.72,237.381,354.159,171.891,358.952,150.509z M250.816,278.882c-0.079,6.328-0.111,11.825-0.095,13.628c0.03,3.403,6.457,9.41,15.533,17.524c3.53,3.155,7.813,6.985,8.984,8.641c-0.794,0.338-1.582,0.693-2.362,1.069c-1.208,0.168-2.619,0.19-4.206,0.209c-3.271,0.04-7.325,0.098-11.724,1.612c-7.352-6.351-18.116-18.122-18.793-22.343c-0.366-2.289-0.5-8.327-0.576-15.135C240.497,283.086,244.846,281.491,250.816,278.882z',
  },
  hawk: {
    // artwork is an eagle silhouette — labeled "Hawk" for a more
    // relatable backyard-bird context, same art either way
    viewBox: '0 0 360.081 360.081',
    path: 'M358.839,130.772c-0.666-0.618-1.432-0.931-2.278-0.931c-3.092,0-6.364,4.36-9.251,8.208c-1.091,1.454-2.527,3.368-3.262,4.005c-0.086-1.467,1.019-5.633,1.85-8.764c2.099-7.914,4.27-16.096,0.735-18c-0.368-0.198-0.757-0.299-1.157-0.299c-2.545,0-4.492,3.814-7.458,10.037c-2.322,4.871-5.211,10.934-7.597,10.934c-0.152,0-0.302-0.026-0.456-0.081c-0.42-0.75-0.383-4.184-0.355-6.71c0.072-6.618,0.153-14.118-4.047-14.678c-0.125-0.017-0.25-0.025-0.374-0.025c-3.63,0-5.748,6.793-7.99,13.986c-1.092,3.504-2.743,8.8-3.677,9.158c-1.255-0.251-3.792-4.038-5.83-7.081c-3.343-4.99-6.533-9.684-9.487-9.441c-3.081,0.257-3.033,4.63-2.983,9.261c0.041,3.803,0.093,8.537-1.81,9.561c-0.184,0.099-0.384,0.147-0.61,0.147c-2.116,0-5.594-3.792-8.389-6.839c-3.259-3.552-5.348-5.73-7.152-5.73c-0.446,0-0.866,0.138-1.214,0.399c-1.985,1.489-1.873,5.99-1.754,10.755c0.06,2.402,0.15,5.988-0.344,6.747c-0.916-0.125-3.528-1.861-5.844-3.398c-5.123-3.402-11.498-7.637-16.64-7.637c-0.846,0-1.641,0.118-2.363,0.351c-5.578,1.796-6.648,4.437-7.356,6.185c-0.371,0.916-0.557,1.33-1.071,1.55c-0.643,0.274-1.683,0.166-2.827-0.007c-0.757-0.115-1.541-0.233-2.374-0.233c-1.837,0-3.357,0.627-4.649,1.919c-1.313,1.313-2.487,2.87-3.623,4.375c-1.689,2.24-3.286,4.356-4.824,4.933c-0.813,0.305-2.441,2.006-7.028,6.88c-10.088,10.717-31.079,33.019-41.837,33.02c-2.013,0-3.517-0.806-4.597-2.464c-1.786-2.741-4.461-7.761-7.848-14.118c-10.695-20.071-26.858-50.404-40.608-57.508C84.014,100.41,52.865,70.21,36.131,53.986c-9.126-8.848-12.368-11.908-14.058-11.908c-0.479,0-0.899,0.218-1.154,0.599c-0.489,0.729-0.313,1.869,0.648,4.208c2.911,7.082,9.584,16.8,14.947,24.608c3.098,4.511,6.55,9.539,7.476,11.644c-2.52-1.166-7.368-6.289-11.35-10.497C25.625,65.23,21.154,60.73,18.201,60.73c-0.564,0-1.063,0.162-1.48,0.479c-2.261,1.718,0.989,6.297,6.928,14.243c2.367,3.167,5.852,7.83,6.29,9.438c-1.261-0.268-4.061-2.483-6.338-4.285c-3.86-3.054-7.853-6.212-10.77-6.212c-0.56,0-1.073,0.115-1.526,0.341c-0.667,0.333-1.102,0.876-1.26,1.571c-0.481,2.12,1.733,5.176,5.167,9.597c1.496,1.925,3.712,4.779,3.886,5.796c-0.138,0.028-0.29,0.042-0.453,0.042c-1.562,0-3.849-1.215-6.061-2.391c-2.423-1.288-4.712-2.504-6.602-2.504c-0.645,0-1.22,0.144-1.709,0.427c-2.151,1.245-0.206,5.114,1.854,9.209c0.563,1.121,1.296,2.578,1.563,3.347c-0.509,0.071-1.345,0.072-1.95,0.073c-1.945,0.003-3.957,0.006-5.05,1.119c-0.46,0.467-0.697,1.086-0.687,1.79c0.042,2.656,42.16,92.95,91.761,127.749c6.636,4.656,9.21,12.982,11.699,21.034c0.909,2.94,1.767,5.717,2.806,8.239c0.374,0.909,0.379,1.669,0.017,2.394c-1.564,3.123-9.652,5.201-18.215,7.4c-4.941,1.27-10.049,2.582-15.005,4.292c-61.734,7.598-61.731,11.024-61.731,12.672c0,3.317,2.206,4.9,3.817,6.056c1.625,1.166,1.86,1.497,1.573,2.215c-0.376,0.941-1.279,1.909-2.234,2.934c-2.065,2.217-4.636,4.975-3.093,9.09c0.558,1.487,2.389,2.21,5.597,2.21c5.546,0,14.548-2.09,21.165-3.857c-14.858,8.494-14.859,10.045-14.859,10.603c0,0.755,0,2.162,8.549,2.162c8.537,0,22.06-1.545,32.073-5.898c3.096-1.346,5.734-2.64,8.285-3.89c2.409-1.181,4.688-2.298,6.98-3.265c26.126,1.41,66.339,3.05,94.063,3.05c15.604,0,25.431-0.522,29.205-1.551c5.059-1.38,10.855-3.62,16.993-5.991c11.324-4.375,23.033-8.9,32.104-8.9c1.857,0,3.552,0.198,5.037,0.589c13.288,3.496,18.372,14.022,18.422,14.128l0.201,0.427l0.456,0.117c0.079,0.02,0.506,0.121,1.167,0.121c0,0,0,0,0,0c1.913,0,6.598-0.903,8.793-9.264c1.29-4.914-1.226-8.538-2.162-9.672c0.235-2.671,0.776-15.885-10.323-24.661c-6.735-5.326-13.414-7.774-17.833-9.395c-2.089-0.766-4.951-1.815-4.901-2.371c0.454-2.894,28.565-60.374,68.724-73.151c31.045-9.878,38.504-29.301,40.27-37.192C360.485,136.389,360.254,132.086,358.839,130.772z',
  },
}

const REFERENCE_BIRDS = [
  { name: 'Hummingbird', cm: 9, variant: 'hummingbird' },
  { name: 'Sparrow', cm: 15, variant: 'sparrow' },
  { name: 'Robin', cm: 25, variant: 'robin' },
  { name: 'Crow', cm: 45, variant: 'crow' },
  { name: 'Hawk', cm: 75, variant: 'hawk' },
]

// Sizes each silhouette renders at — bigger toward the large end, matching
// relative size, but all large enough that the artwork's detail
// shows (the hand-drawn attempts this replaced were 14–34px,
// too small for any shape to read clearly regardless of the art itself).
// Render sizes are now computed from each reference bird's own cm
// value (sqrt-scaled, not linear — cm differences among small birds
// matter more visually than the same absolute difference among large
// ones) rather than hand-picked fixed pixel sizes. Reported directly:
// the old fixed range (34–58px, under 2x) didn't read as visually
// distinct enough to "reflect changing size." This range (26–68px, over
// 2.5x) does, verified against the reference cm values before
// shipping.
// Reported directly with a screenshot: Crow and Hawk (the two largest
// icons, sitting relatively close together on the log scale — 70.5%
// and 89.9%) were crowding each other. Confirmed by computing exact
// pixel gaps at a realistic card width: Crow-to-Hawk was only ~5px vs.
// 25-35px between every other pair. Reduced the max size from 68 to 52
// (verified this brings the tightest gap up to ~20px, much closer to
// the others) rather than widening the scale itself, which would have
// meant shrinking the gaps everywhere else instead of just where the
// two big birds crowd.
const SIZE_PX_MIN = 22, SIZE_PX_MAX = 52
function iconSizeFor(cm) {
  const minCm = REFERENCE_BIRDS[0].cm, maxCm = REFERENCE_BIRDS[REFERENCE_BIRDS.length - 1].cm
  const ratio = Math.sqrt(cm - minCm) / Math.sqrt(maxCm - minCm)
  return Math.round(SIZE_PX_MIN + (SIZE_PX_MAX - SIZE_PX_MIN) * ratio)
}

// Switched from a linear to a log scale (direct, reported observation:
// with 5 reference points spanning almost 10x — 9cm to 75cm — a linear
// scale clusters Hummingbird/Sparrow/Pigeon/Crow into the left half
// while Hawk sits alone with a big empty gap. Verified with the 
// reference values before switching: log spacing is 17.1/25.3/11.3/17.1
// percentage points between adjacent birds vs. linear's much less even
// 5.4/15.5/11.8/27.3. Also matches how bird-size differences are
// perceived — proportionally, not additively (the jump from
// Hummingbird to Sparrow feels bigger than the same absolute cm
// difference would at the Crow/Hawk end).
const SCALE_MIN_CM = 7 // reported gap: the earlier 5-100 bounds
const SCALE_MAX_CM = 98 // left ~20% of the width empty before Hummingbird
                          // even started. Tightened so the birds
                          // themselves span roughly 9.5%-89.9% of the
                          // width — close to symmetric margins on both
                          // sides — while still keeping enough headroom
                          // that neither end sits flush against the edge.
const LOG_MIN = Math.log10(SCALE_MIN_CM)
const LOG_MAX = Math.log10(SCALE_MAX_CM)
const CM_PER_IN = 2.54
const AMBIGUOUS_MARGIN = 0.15

function pct(cm) {
  const clamped = Math.min(SCALE_MAX_CM, Math.max(SCALE_MIN_CM, cm))
  const logCm = Math.log10(clamped)
  return Math.min(100, Math.max(0, ((logCm - LOG_MIN) / (LOG_MAX - LOG_MIN)) * 100))
}

// "Nearest" and "in-between" are now determined in the same log space as
// the visual positions above, rather than raw cm — keeps the highlighted
// dot(s) and caption consistent with what's nearest on the
// (now log-scaled) ruler, instead of the two disagreeing.
// When the bird being viewed IS (or is a specific species of) the
// reference bird itself, phrasing like "About Pigeon-sized" or
// "Pigeon-sized or smaller" reads oddly on that exact bird's own
// profile — reported directly, comparing a pigeon's own profile against
// "Pigeon" as if it were a different reference bird. Detected via a
// simple substring match (e.g. "Rock Pigeon" contains "Pigeon", "Ruby-
// throated Hummingbird" contains "Hummingbird") rather than an exact
// species list, since the reference names are generic categories that
// legitimately span several species. Only applied to a clean single
// match — the "Between X and Y-sized" phrasing is left alone even if the
// bird happens to share one of those two names, since it's already
// conveying nuance (this size falls between two categories) rather
// than a comparison to something else.
function isSelfReference(commonName, refName) {
  return !!commonName && commonName.toLowerCase().includes(refName.toLowerCase())
}

function findSizeMatch(avgCm, commonName) {
  const n = REFERENCE_BIRDS.length
  if (avgCm <= REFERENCE_BIRDS[0].cm) {
    const name = REFERENCE_BIRDS[0].name
    return { indices: [0], caption: isSelfReference(commonName, name) ? `${name}-sized` : `${name}-sized or smaller` }
  }
  if (avgCm >= REFERENCE_BIRDS[n - 1].cm) {
    const name = REFERENCE_BIRDS[n - 1].name
    return { indices: [n - 1], caption: isSelfReference(commonName, name) ? `${name}-sized` : `${name}-sized or larger` }
  }
  for (let i = 0; i < n - 1; i++) {
    const lo = REFERENCE_BIRDS[i].cm, hi = REFERENCE_BIRDS[i + 1].cm
    if (avgCm >= lo && avgCm <= hi) {
      const logLo = Math.log10(lo), logHi = Math.log10(hi), logAvg = Math.log10(avgCm)
      const frac = (logAvg - logLo) / (logHi - logLo)
      if (frac >= 0.5 - AMBIGUOUS_MARGIN && frac <= 0.5 + AMBIGUOUS_MARGIN) {
        return { indices: [i, i + 1], caption: `Between ${REFERENCE_BIRDS[i].name} and ${REFERENCE_BIRDS[i + 1].name}-sized` }
      }
      const nearest = frac < 0.5 ? i : i + 1
      const name = REFERENCE_BIRDS[nearest].name
      return { indices: [nearest], caption: isSelfReference(commonName, name) ? `${name}-sized` : `About ${name}-sized` }
    }
  }
  return { indices: [0], caption: `${REFERENCE_BIRDS[0].name}-sized or smaller` }
}

function BirdSilhouette({ variant, cm, filled }) {
  const { viewBox, path, flip, groupTransform } = BIRD_SVGS[variant]
  const size = iconSizeFor(cm)
  const color = filled ? 'var(--accent-400)' : 'var(--text-tertiary)'
  const vbWidth = parseFloat(viewBox.split(' ')[2])
  const flipTransform = flip ? `translate(${vbWidth}, 0) scale(-1, 1)` : undefined
  return (
    <svg viewBox={viewBox} width={size} height={size} style={{ flexShrink: 0 }}>
      <g transform={groupTransform}>
        <path d={path} fill={color} transform={flipTransform}/>
      </g>
    </svg>
  )
}

export default function BirdSizeRuler({ minCm, maxCm, commonName }) {
  if (!minCm || !maxCm) return null

  const avgCm = (minCm + maxCm) / 2
  const { indices: highlighted, caption } = findSizeMatch(avgCm, commonName)

  const minIn = (minCm / CM_PER_IN)
  const maxIn = (maxCm / CM_PER_IN)
  const fmtIn = (v) => (v % 1 === 0 ? v.toFixed(0) : v.toFixed(1))
  const fmtCm = (v) => (v % 1 === 0 ? v.toFixed(0) : v.toFixed(1))
  const sizeText = minCm === maxCm
    ? `${fmtCm(minCm)} cm (${fmtIn(minIn)} in)`
    : `${fmtCm(minCm)}\u2013${fmtCm(maxCm)} cm (${fmtIn(minIn)}\u2013${fmtIn(maxIn)} in)`

  const rangeLeft = pct(minCm)
  const rangeRight = pct(maxCm)
  // Guarantee a minimum visible width — a species with a very narrow
  // reported range would otherwise render as an invisible sliver.
  const rangeWidth = Math.max(rangeRight - rangeLeft, 2.5)

  // The callout anchors to the range bar's own true center position
  // (which can fall anywhere continuously, including between two
  // reference points) rather than snapping to whichever reference dot
  // is nearest — the number should sit above the range it
  // describes, not above the nearest named bird.
  const calloutLeft = Math.min(95, Math.max(5, (rangeLeft + rangeRight) / 2))
  // reported bug: centering text on a point near either edge
  // (translateX(-50%)) pushes roughly half its width past that edge
  // regardless of the point's own percentage — clamping the PERCENTAGE
  // doesn't help, since it's the text's pixel width doing the
  // clipping, confirmed from a screenshot showing "14–17 cm..."
  // cut off on the left. Fixed by switching alignment near the edges:
  // close to the left edge, the text grows rightward from that point
  // instead of being centered on it (and vice versa on the right),
  // so its own width never has anywhere to overflow past the edge.
  const calloutTransform =
    calloutLeft < 20 ? 'translateX(0%)' :
    calloutLeft > 80 ? 'translateX(-100%)' :
    'translateX(-50%)'

  return (
    <div className="w-full">
      <div className="text-xs font-medium mb-3" style={{ color: 'var(--text-tertiary)' }}>Size</div>

      <div className="relative h-5">
        <div className="absolute text-sm font-semibold whitespace-nowrap"
             style={{ left: `${calloutLeft}%`, transform: calloutTransform, color: 'var(--text-primary)' }}>
          {sizeText}
        </div>
      </div>

      {/* Reference silhouettes row — mt-2 (was mt-1) gives the size text
          above a little breathing room; it was rendering close
          enough to the tallest silhouettes (hawk's spread wings) to
          feel cramped, per direct feedback. Kept deliberately small
          rather than adding a lot of empty space. */}
      <div className="relative mt-2 mb-1.5" style={{ height: SIZE_PX_MAX + 8 }}>
        {REFERENCE_BIRDS.map((ref, i) => (
          <div key={ref.name}
               className="absolute bottom-0 flex flex-col items-center"
               style={{ left: `${pct(ref.cm)}%`, transform: 'translateX(-50%)' }}
               title={`${ref.name} (~${ref.cm} cm)`}>
            <BirdSilhouette variant={ref.variant} cm={ref.cm} filled={highlighted.includes(i)}/>
          </div>
        ))}
      </div>

      {/* Ruler: a thin base line spanning the full scale, with a bold
          highlighted segment showing this species' measured range
          at its true continuous position (can fall anywhere, including
          between two reference points — not snapped to one of them),
          plus small dots at each fixed reference point. The nearest
          reference dot(s) are enlarged and filled, showing which named
          bird this size is closest to, while the bold segment itself
          shows the range independently of that. */}
      <div className="relative h-2">
        <div className="absolute top-1/2 left-0 right-0 h-px" style={{ background: 'var(--border-default)', transform: 'translateY(-50%)' }}/>
        <div className="absolute top-1/2 rounded-full"
             style={{
               left: `${rangeLeft}%`,
               width: `${rangeWidth}%`,
               height: 4,
               background: 'var(--accent-400)',
               transform: 'translateY(-50%)',
             }}/>
        {REFERENCE_BIRDS.map((ref, i) => {
          const isHi = highlighted.includes(i)
          return (
            <div key={ref.name}
                 className="absolute top-1/2 rounded-full"
                 style={{
                   left: `${pct(ref.cm)}%`,
                   width: isHi ? 12 : 7,
                   height: isHi ? 12 : 7,
                   transform: 'translate(-50%, -50%)',
                   background: isHi ? 'var(--accent-400)' : 'var(--bg-card)',
                   border: isHi ? 'none' : '1.5px solid var(--border-default)',
                 }}/>
          )
        })}
      </div>

      <div className="text-center text-xs mt-2.5" style={{ color: 'var(--text-secondary)' }}>
        {caption}
      </div>
    </div>
  )
}
