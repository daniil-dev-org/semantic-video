# Manual Download Instructions

Because the Kaggle API credentials (`~/.kaggle/kaggle.json`) were not found in the current environment, the automatic download of the primary dataset was skipped.

## How to download the YouTube Trending Video Dataset

1. **Create a Kaggle Account:** Go to [Kaggle](https://www.kaggle.com) and sign up/log in.
2. **Generate API Token:**
   - Go to your Account settings (click on your profile picture -> Settings).
   - Scroll down to the "API" section.
   - Click "Create New Token". This will download a `kaggle.json` file.
3. **Place the Token:**
   - Put `kaggle.json` in `C:\Users\<YourUsername>\.kaggle\kaggle.json` (Windows) or `~/.kaggle/kaggle.json` (Mac/Linux).
4. **Download via CLI:**
   ```bash
   pip install kaggle
   kaggle datasets download -d rsrishav/youtube-trending-video-dataset -p data/raw/yt_trending_kaggle --unzip
   ```
5. **Alternatively, Download Manually:**
   - Visit [YouTube Trending Video Dataset](https://www.kaggle.com/datasets/rsrishav/youtube-trending-video-dataset).
   - Click "Download" (approx. 2 GB).
   - Extract the `.csv` files into the `data/raw/yt_trending_kaggle/` directory.

Once the files are in `data/raw/yt_trending_kaggle/`, you can run the import script:
```bash
python run_import_dataset.py --source youtube_trending --input data/raw/yt_trending_kaggle --output samples/input/metadata_snapshots.csv
```
