import pytest
from stp.sidecar_schema import GlobalFeatures, SidecarDocument, AssetInfo, VideoFeatures
from pydantic import ValidationError

def test_global_features_has_new_fields():
    gf = GlobalFeatures(edge_density_avg=0.5, hook_motion_0_3s=0.2)
    assert gf.edge_density_avg == 0.5
    assert gf.hook_motion_0_3s == 0.2

def test_sidecar_validation():
    asset = AssetInfo(asset_id="123", source_name="video.mp4")
    doc = SidecarDocument(asset=asset, video_features=VideoFeatures())
    assert doc.stp_version == "0.1"
