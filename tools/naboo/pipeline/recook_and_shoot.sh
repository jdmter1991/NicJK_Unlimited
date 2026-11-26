#!/bin/bash
# Recook the world, rebuild DDS + vertex AO (keeps .tsky), then take the ground / palace comparison shots.
#   recook_and_shoot.sh <tag>      -> ref/cmp_ground_<tag>.jpg, shots_<tag>/palace_and_statues.jpg
TAG=${1:-new}
R="/e/jedi academy modding archive/TaystJK_AI_Claude_Code_improvements"; D="$R/devgame_naboo"
cd "$R/naboo" || exit 1
py tools/cook_v1.py export/city naboo_theed ../devgame_naboo/nicjk > export/city/cook_$TAG.log 2>&1 || { tail -5 export/city/cook_$TAG.log; exit 1; }
grep -o '"missing_textures": [^]]*]\|"glow[a-z_]*": [0-9]*\|"world_projected": [0-9]*|"still_plants": [0-9]*|"crystal_glass": [0-9]*\|"instances": [0-9]*' export/city/cook_$TAG.log
py tools/convert_textures_dds.py ../devgame_naboo/nicjk 2>&1 | tail -1 | cut -c1-60
build_tools/bake_vertex_ao.exe ../devgame_naboo/nicjk/maps/naboo_theed.tworld ../devgame_naboo/nicjk/maps/naboo_theed.tao 96 24 | cut -c1-70
cd "$D" && rm -f nicjk/screenshots/*.jpg nicjk/qconsole.log
timeout 600 ./nicjk.x86_64.exe +set fs_basepath "E:\jedi academy modding archive\Jedi Academy TaystJK_AI test\GameData" +set fs_homepath "$(cygpath -w "$D")" +set fs_game nicjk +set cl_renderer rd-vulkant +set r_mode -1 +set r_fullscreen 0 +set r_tworldPBR 1 +set r_tworldShadows 1 +set r_customwidth 1280 +set r_customheight 720 +set net_port 29181 +set logfile 2 +set com_maxfps 125 +devmap naboo_theed +exec naboo_ground.cfg > client_test.out 2>&1
grep -a "ERROR\|does not match" nicjk/qconsole.log | head -3
mkdir -p "$R/naboo/export/city/shots_$TAG"; cd nicjk/screenshots && py -c "
from PIL import Image; import glob
fs=sorted(glob.glob('shot*.jpg')); R=r'$(cygpath -w "$R/naboo/export/city")'; print(len(fs),'shots')
names=['gnd_court_a','gnd_court_b','gnd_court_c','gnd_river_a','gnd_river_b','gnd_river_c']
s=Image.new('RGB',(1920,1620))
for i,n in enumerate(names):
    r=i%3; c=i//3
    s.paste(Image.open(R+'/ref/ref_%s.png'%n).convert('RGB').resize((480,540)),(960*c,540*r)); s.paste(Image.open(fs[i]).resize((480,540)),(960*c+480,540*r))
s.save(R+'/ref/cmp_ground_$TAG.jpg',quality=86)
s=Image.new('RGB',(1920,720))
for i,f in enumerate(fs[6:12]): s.paste(Image.open(f).resize((640,360)),(640*(i%3),360*(i//3)))
s.save(R+'/shots_$TAG/palace_and_statues.jpg',quality=88)
Image.open(fs[0]).save(R+'/shots_$TAG/court_a.jpg',quality=90)"
