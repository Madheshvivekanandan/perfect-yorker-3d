#!/usr/bin/env bash
# Downloads every free asset the pipeline needs and installs the MPFB (MakeHuman) Blender extension.
# All sources are free: MPFB (GPL), MakeHuman system assets (CC0), Poly Haven (CC0), CMU mocap (free for any use).
set -euo pipefail

BLENDER="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
ROOT="$(cd "$(dirname "$0")" && pwd)"
A="$ROOT/assets"
mkdir -p "$A"/{hdri,tex,mocap,addons,mh}

echo "==> MPFB 2 (MakeHuman plugin for Blender)"
curl -sL -o "$A/addons/mpfb.zip" \
  "https://extensions.blender.org/download/sha256:4f0a879d64a39bf646fbf5f53601ac678855da329d650617dca5737548239a87/add-on-mpfb-v2.0.17.zip"
"$BLENDER" -b --factory-startup --command extension install-file -r user_default -e "$A/addons/mpfb.zip"

echo "==> MakeHuman CC0 system assets (skins, hair, eyes, clothes) ~280 MB"
curl -L -o "$A/mh_assets.zip" \
  "http://files.makehumancommunity.org/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip"
unzip -q -o "$A/mh_assets.zip" -d "$A/mh" && rm "$A/mh_assets.zip"
# MPFB looks for user assets in its extension data folder
MPFB_DATA="$("$BLENDER" -b --python-expr \
  "from bl_ext.user_default.mpfb.services.locationservice import LocationService as L; print('MPFBDATA=' + L.get_user_data())" \
  2>/dev/null | sed -n 's/^MPFBDATA=//p')"
mkdir -p "$MPFB_DATA" && cp -R "$A/mh/"* "$MPFB_DATA/"

echo "==> Poly Haven HDRI + textures (CC0)"
curl -sL -o "$A/hdri/stadium_01.exr" "https://dl.polyhaven.org/file/ph-assets/HDRIs/exr/4k/stadium_01_4k.exr"
for t in grass_ground dry_ground_01 sparse_grass; do
  curl -s "https://api.polyhaven.com/files/$t" | "$BLENDER" -b --python-expr "
import json, sys
d = json.load(sys.stdin)
for k in ['Diffuse', 'nor_gl', 'Rough', 'Displacement']:
    if k in d: print('URL', k, d[k]['2k']['jpg']['url'])" 2>/dev/null | sed -n 's/^URL //p' |
  while read -r k u; do curl -sL -o "$A/tex/${t}_$k.jpg" "$u"; done
done

echo "==> CMU motion capture (BVH, cgspeed conversion)"
for f in 016/16_55 009/09_01; do
  curl -sL -o "$A/mocap/$(basename $f).bvh" "https://raw.githubusercontent.com/una-dinosauria/cmu-mocap/master/data/$f.bvh"
done
echo "Done. Next: $BLENDER -b --python scripts/build.py"
