import os
import pandas as pd
import numpy as np
from datetime import timedelta

os.makedirs("data/raw/yt_trending_kaggle", exist_ok=True)

# Generate a small sample that matches Kaggle YouTube Trending schema
# columns: video_id,title,publishedAt,channelId,channelTitle,categoryId,trending_date,tags,view_count,likes,dislikes,comment_count,thumbnail_link,comments_disabled,ratings_disabled,description

rows = []
base_date = pd.to_datetime("2023-01-01T00:00:00Z")

for i in range(1, 101):  # 100 videos
    video_id = f"vid_{i:04d}"
    published_at = base_date - timedelta(days=np.random.randint(1, 10))
    
    # 10 days of snapshots for each video
    base_views = np.random.randint(1000, 50000)
    growth_rate = np.random.uniform(1.01, 1.5)  # Add variance!
    for d in range(10):
        trending_date = (published_at + timedelta(days=d)).strftime("%y.%d.%m") # Kaggle format is YY.DD.MM
        views = int(base_views * (growth_rate ** d))
        likes = int(views * 0.05)
        comments = int(likes * 0.1)
        
        rows.append({
            "video_id": video_id,
            "title": f"Test Video {i}",
            "publishedAt": published_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "channelId": f"chan_{i % 10}",
            "channelTitle": f"Channel {i % 10}",
            "categoryId": str(np.random.randint(1, 30)),
            "trending_date": trending_date,
            "tags": "test|video|trend",
            "view_count": views,
            "likes": likes,
            "dislikes": 0,
            "comment_count": comments,
            "thumbnail_link": "http://example.com/thumb.jpg",
            "comments_disabled": "False",
            "ratings_disabled": "False",
            "description": "Test description"
        })

df = pd.DataFrame(rows)
df.to_csv("data/raw/yt_trending_kaggle/US_youtube_trending_data.csv", index=False)
print(f"Generated fake Kaggle data: {len(df)} rows")
