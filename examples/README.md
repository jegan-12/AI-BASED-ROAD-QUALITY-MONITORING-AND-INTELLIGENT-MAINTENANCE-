# Synthetic metadata fixtures

These coordinates and timestamps are invented input examples, not recorded road surveys. Replace them with the capture device's actual fixes for real use. The GPS track covers only four seconds; longer videos need longer tracks. Upload `video-gps-track.json` in the dashboard's GPS field when testing a video no longer than four seconds.

To exercise image/video ingestion without supplying personal media, run `python -m scripts.smoke`. It creates temporary gray images and a short synthetic video, processes them through the actual HTTP services, checks review/export and removes its test data. It reports no model accuracy.
