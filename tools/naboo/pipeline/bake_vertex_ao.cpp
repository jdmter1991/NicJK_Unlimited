// Ambient occlusion per vertex of the cooked world -> maps/<name>.tao
//   bake_vertex_ao <game_dir>/taystjk/maps/<name>.tworld <out.tao> [reach_units] [rays]
// For every mesh and each of its detail levels the opaque, static triangles are put into a bounding volume
// hierarchy. From every vertex of that level `rays` cosine-distributed rays are cast into the
// hemisphere around its normal; the share that hits the mesh itself within `reach_units` (default 96 = about 2.4 m)
// is the occlusion. This is the mesh's own occlusion (window reveals, cornices, arcades, column flutes): it is
// the same for every placement of the mesh, so it can live in the shared vertex data. Occlusion by neighbouring
// placements is not included (see tools/bake_sky_occlusion.py for the per-placement sky occlusion).
// Blended materials and animated ones (foliage, cloth, water, glow, billboards) neither cast nor receive.
// File: "TAO1", version 1, vertex count, then one byte per vertex: 255 = open, 0 = fully occluded.
// Single-threaded on purpose; the whole map takes about a minute.
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <cmath>
#include <vector>
#include <algorithm>
#include <chrono>

#pragma pack(push, 1)
struct Header { char magic[4]; uint32_t version, numMaterials, numMeshes, numSubmeshes, numInstances, numVerts, numIndexes; float f[16]; uint32_t reserved[4]; };
struct Material { char shader[64]; float tint[3]; uint32_t flags; };
struct Mesh { uint32_t firstVert, numVerts, firstIndex, numIndexes, numLods, lodFirstSub[3], lodNumSubs[3]; float center[3], radius; };
struct Submesh { uint32_t material, firstIndex, numIndexes, reserved; };
struct Instance { uint32_t mesh; float m[12], center[3], radius; };
struct Vertex { float xyz[3], normal[3], st[2]; };
#pragma pack(pop)

struct V3 { float x, y, z; };
static inline V3 operator-(V3 a, V3 b) { return { a.x - b.x, a.y - b.y, a.z - b.z }; }
static inline V3 operator+(V3 a, V3 b) { return { a.x + b.x, a.y + b.y, a.z + b.z }; }
static inline V3 operator*(V3 a, float s) { return { a.x * s, a.y * s, a.z * s }; }
static inline float dot(V3 a, V3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
static inline V3 cross(V3 a, V3 b) { return { a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x }; }

struct Tri { V3 a, e1, e2, n; };		// n: unit normal
struct Node { float lo[3], hi[3]; int left, right, first, count; };	// leaf: count > 0

static std::vector<Tri> tris;
static std::vector<Node> nodes;
static std::vector<int> order;

static int build(int first, int count)
{
	Node n; n.left = n.right = -1; n.first = first; n.count = count;
	for (int k = 0; k < 3; k++) { n.lo[k] = 1e30f; n.hi[k] = -1e30f; }
	float clo[3] = { 1e30f, 1e30f, 1e30f }, chi[3] = { -1e30f, -1e30f, -1e30f };
	for (int i = first; i < first + count; i++) {
		const Tri &t = tris[order[i]];
		V3 p[3] = { t.a, t.a + t.e1, t.a + t.e2 };
		float c[3] = { 0, 0, 0 };
		for (int j = 0; j < 3; j++) {
			float v[3] = { p[j].x, p[j].y, p[j].z };
			for (int k = 0; k < 3; k++) { n.lo[k] = std::min(n.lo[k], v[k]); n.hi[k] = std::max(n.hi[k], v[k]); c[k] += v[k] / 3.0f; }
		}
		for (int k = 0; k < 3; k++) { clo[k] = std::min(clo[k], c[k]); chi[k] = std::max(chi[k], c[k]); }
	}
	int idx = (int)nodes.size();
	nodes.push_back(n);
	if (count <= 4)
		return idx;
	int axis = 0;
	if (chi[1] - clo[1] > chi[axis] - clo[axis]) axis = 1;
	if (chi[2] - clo[2] > chi[axis] - clo[axis]) axis = 2;
	if (chi[axis] - clo[axis] < 1e-6f)
		return idx;
	int mid = first + count / 2;
	std::nth_element(order.begin() + first, order.begin() + mid, order.begin() + first + count, [axis](int x, int y) {
		const Tri &tx = tris[x], &ty = tris[y];
		const float cx = axis == 0 ? tx.a.x * 3 + tx.e1.x + tx.e2.x : axis == 1 ? tx.a.y * 3 + tx.e1.y + tx.e2.y : tx.a.z * 3 + tx.e1.z + tx.e2.z;
		const float cy = axis == 0 ? ty.a.x * 3 + ty.e1.x + ty.e2.x : axis == 1 ? ty.a.y * 3 + ty.e1.y + ty.e2.y : ty.a.z * 3 + ty.e1.z + ty.e2.z;
		return cx < cy; });
	int l = build(first, mid - first);
	int r = build(mid, first + count - mid);
	nodes[idx].left = l; nodes[idx].right = r; nodes[idx].count = 0;
	return idx;
}

// pn, pd: the plane of the surface the ray starts from. Triangles lying in (nearly) that plane are skipped: trim
// and decal layers float a centimetre in front of walls and would otherwise black out the wall behind them.
static bool anyHit(V3 o, V3 d, float tmax, V3 pn, float pd)
{
	const float inv[3] = { 1.0f / (std::fabs(d.x) > 1e-9f ? d.x : 1e-9f), 1.0f / (std::fabs(d.y) > 1e-9f ? d.y : 1e-9f), 1.0f / (std::fabs(d.z) > 1e-9f ? d.z : 1e-9f) };
	const float oo[3] = { o.x, o.y, o.z };
	int stack[64], sp = 0;
	stack[sp++] = 0;
	while (sp) {
		const Node &n = nodes[stack[--sp]];
		float t0 = 0.0f, t1 = tmax;
		bool miss = false;
		for (int k = 0; k < 3; k++) {
			float a = (n.lo[k] - oo[k]) * inv[k], b = (n.hi[k] - oo[k]) * inv[k];
			if (a > b) std::swap(a, b);
			t0 = std::max(t0, a); t1 = std::min(t1, b);
			if (t0 > t1) { miss = true; break; }
		}
		if (miss)
			continue;
		if (n.count > 0) {
			for (int i = n.first; i < n.first + n.count; i++) {
				const Tri &t = tris[order[i]];
				if (std::fabs(dot(t.n, pn)) > 0.95f && std::fabs(dot(pn, t.a) - pd) < 6.0f)
					continue;
				const V3 p = cross(d, t.e2);
				const float det = dot(t.e1, p);
				if (std::fabs(det) < 1e-12f)
					continue;
				const float id = 1.0f / det;
				const V3 s = o - t.a;
				const float u = dot(s, p) * id;
				if (u < 0.0f || u > 1.0f)
					continue;
				const V3 q = cross(s, t.e1);
				const float v = dot(d, q) * id;
				if (v < 0.0f || u + v > 1.0f)
					continue;
				const float tt = dot(t.e2, q) * id;
				if (tt > 0.0f && tt < tmax)
					return true;
			}
		} else if (sp < 62) {
			stack[sp++] = n.left; stack[sp++] = n.right;
		}
	}
	return false;
}

int main(int argc, char **argv)
{
	if (argc < 3) { std::printf("usage: bake_vertex_ao <in.tworld> <out.tao> [reach_units] [rays]\n"); return 1; }
	const float reach = argc > 3 ? (float)std::atof(argv[3]) : 96.0f;
	const int NR = argc > 4 ? std::atoi(argv[4]) : 24;
	const auto t0 = std::chrono::steady_clock::now();
	FILE *f = std::fopen(argv[1], "rb");
	if (!f) { std::printf("cannot open %s\n", argv[1]); return 1; }
	Header h;
	if (std::fread(&h, sizeof(h), 1, f) != 1 || std::memcmp(h.magic, "TWLD", 4)) { std::printf("not a cooked world\n"); return 1; }
	std::vector<Material> mats(h.numMaterials); std::vector<Mesh> meshes(h.numMeshes); std::vector<Submesh> subs(h.numSubmeshes);
	std::vector<Vertex> verts(h.numVerts); std::vector<uint32_t> idx(h.numIndexes);
	bool ok = std::fread(mats.data(), sizeof(Material), mats.size(), f) == mats.size()
		&& std::fread(meshes.data(), sizeof(Mesh), meshes.size(), f) == meshes.size()
		&& std::fread(subs.data(), sizeof(Submesh), subs.size(), f) == subs.size()
		&& std::fseek(f, (long)((long long)h.numInstances * sizeof(Instance)), SEEK_CUR) == 0
		&& std::fread(verts.data(), sizeof(Vertex), verts.size(), f) == verts.size()
		&& std::fread(idx.data(), 4, idx.size(), f) == idx.size();
	std::fclose(f);
	if (!ok) { std::printf("short read\n"); return 1; }

	// a fixed set of cosine-distributed directions in the frame (tangent, bitangent, normal)
	std::vector<V3> dirs;
	for (int i = 0; i < NR; i++) {
		const float u = (i + 0.5f) / NR, v = std::fmod(i * 0.61803399f, 1.0f);
		const float r = std::sqrt(u), ph = 6.2831853f * v;
		dirs.push_back({ r * std::cos(ph), r * std::sin(ph), std::sqrt(1.0f - u) });
	}
	std::vector<uint8_t> ao(h.numVerts, 255);
	std::vector<uint8_t> receives(h.numVerts);
	long long rays = 0, shaded = 0; int baked = 0;
	for (uint32_t mi = 0; mi < h.numMeshes; mi++) {
		const Mesh &m = meshes[mi];
		for (uint32_t l = 0; l < m.numLods && l < 3; l++) {
		// every detail level against its own triangles: a simplified level lies slightly inside or outside the
		// full one, so testing it against the full surface would call most of its vertices occluded
		tris.clear(); nodes.clear(); order.clear();
		std::fill(receives.begin() + m.firstVert, receives.begin() + m.firstVert + m.numVerts, (uint8_t)0);
		for (uint32_t s = m.lodFirstSub[l]; s < m.lodFirstSub[l] + m.lodNumSubs[l]; s++) {
			const Submesh &sb = subs[s];
			const uint32_t fl = mats[sb.material].flags;
			if ((fl & 1) || ((fl >> 1) & 7) != 0)
				continue;					// blended or animated
			for (uint32_t k = 0; k + 2 < sb.numIndexes; k += 3) {
				const uint32_t i0 = idx[m.firstIndex + sb.firstIndex + k], i1 = idx[m.firstIndex + sb.firstIndex + k + 1], i2 = idx[m.firstIndex + sb.firstIndex + k + 2];
				if (i0 >= m.numVerts || i1 >= m.numVerts || i2 >= m.numVerts)
					continue;
				receives[m.firstVert + i0] = receives[m.firstVert + i1] = receives[m.firstVert + i2] = 1;
				const Vertex &a = verts[m.firstVert + i0], &b = verts[m.firstVert + i1], &c = verts[m.firstVert + i2];
				const V3 pa = { a.xyz[0], a.xyz[1], a.xyz[2] }, pb = { b.xyz[0], b.xyz[1], b.xyz[2] }, pc = { c.xyz[0], c.xyz[1], c.xyz[2] };
				V3 tn = cross(pb - pa, pc - pa); const float tl = std::sqrt(dot(tn, tn));
				if (tl < 1e-9f)
					continue;
				tris.push_back({ pa, pb - pa, pc - pa, tn * (1.0f / tl) });
			}
		}
		if (tris.size() < 4)
			continue;
		order.resize(tris.size());
		for (size_t i = 0; i < order.size(); i++) order[i] = (int)i;
		nodes.reserve(tris.size() * 2);
		build(0, (int)tris.size());
		if (l == 0) baked++;
		for (uint32_t vi = m.firstVert; vi < m.firstVert + m.numVerts; vi++) {
			if (!receives[vi])
				continue;
			const Vertex &v = verts[vi];
			V3 n = { v.normal[0], v.normal[1], v.normal[2] };
			const float nl = std::sqrt(dot(n, n));
			if (nl < 1e-6f)
				continue;
			n = n * (1.0f / nl);
			const V3 up = std::fabs(n.z) < 0.9f ? V3{ 0, 0, 1 } : V3{ 1, 0, 0 };
			V3 t = cross(up, n); t = t * (1.0f / std::sqrt(dot(t, t)));
			const V3 b = cross(n, t);
			// rotate the direction set by an angle that depends on the vertex, so neighbours do not share a pattern
			const float ang = 6.2831853f * std::fmod(v.xyz[0] * 0.137f + v.xyz[1] * 0.251f + v.xyz[2] * 0.379f, 1.0f);
			const float ca = std::cos(ang), sa = std::sin(ang);
			const V3 o = V3{ v.xyz[0], v.xyz[1], v.xyz[2] } + n * 0.75f;
			int hit = 0;
			for (int i = 0; i < NR; i++) {
				const float dx = dirs[i].x * ca - dirs[i].y * sa, dy = dirs[i].x * sa + dirs[i].y * ca;
				const V3 d = t * dx + b * dy + n * dirs[i].z;
				if (anyHit(o, d, reach, n, dot(n, V3{ v.xyz[0], v.xyz[1], v.xyz[2] })))
					hit++;
			}
			rays += NR; shaded++;
			ao[vi] = (uint8_t)(255.0f * (1.0f - (float)hit / NR) + 0.5f);
		}
		}
	}
	FILE *o = std::fopen(argv[2], "wb");
	if (!o) { std::printf("cannot write %s\n", argv[2]); return 1; }
	const uint32_t head[2] = { 1, h.numVerts };
	std::fwrite("TAO1", 1, 4, o); std::fwrite(head, 4, 2, o); std::fwrite(ao.data(), 1, ao.size(), o); std::fclose(o);
	long long hist[5] = { 0, 0, 0, 0, 0 }; double sum = 0;
	for (uint32_t i = 0; i < h.numVerts; i++) { hist[std::min(4, ao[i] / 52)]++; sum += ao[i]; }
	const double sec = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
	std::printf("{\"seconds\": %.1f, \"meshes\": %u, \"meshes_baked\": %d, \"vertices\": %u, \"vertices_shaded\": %lld, \"rays\": %lld, \"reach_units\": %.0f, \"rays_per_vertex\": %d,\n \"mean_openness\": %.3f, \"vertices_by_openness_0_20_40_60_80_100_percent\": [%lld, %lld, %lld, %lld, %lld]}\n",
		sec, h.numMeshes, baked, h.numVerts, shaded, rays, reach, NR, sum / 255.0 / h.numVerts, hist[0], hist[1], hist[2], hist[3], hist[4]);
	return 0;
}
