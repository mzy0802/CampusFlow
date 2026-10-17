import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import {cameraPlan,addRoadCamera,cameraSector,exteriorCorners} from '../src/cameraGeometry.js'

test('planned cameras mount on real teaching-building exterior vertices with short sectors',()=>{
 const buildings=JSON.parse(fs.readFileSync(new URL('../../data/buildings.osm.geojson',import.meta.url))).features
 const areas=JSON.parse(fs.readFileSync(new URL('../../data/parking.imported.geojson',import.meta.url))).features.map(f=>{const r=f.geometry.coordinates[0].slice(0,-1);return {...f.properties,longitude:r.reduce((s,p)=>s+p[0],0)/r.length,latitude:r.reduce((s,p)=>s+p[1],0)/r.length}})
 const roads=JSON.parse(fs.readFileSync(new URL('../../data/roads.osm.geojson',import.meta.url))).features
 const cameras=addRoadCamera(cameraPlan(areas,buildings),buildings,roads)
 assert.ok(cameras.length>=5)
 for(const c of cameras){
  const f=buildings.find(f=>f.properties.id===c.building_id)
  assert.ok(exteriorCorners(f.geometry.coordinates[0]).some(p=>p[0]===c.point[0]&&p[1]===c.point[1]))
  assert.ok(c.radius<=42&&c.fov<=60)
  const sector=cameraSector(c);assert.deepEqual(sector[0],[c.point[1],c.point[0]]);assert.deepEqual(sector.at(-1),sector[0])
  assert.equal(sector.length,23)
 }
})
