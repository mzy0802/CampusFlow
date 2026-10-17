import test from 'node:test'
import assert from 'node:assert/strict'
import {areaSurroundSpots} from '../src/parkingPlacement.js'
import {inside} from '../src/simulationMath.js'

test('violations cluster around the parking area but never inside it or inside buildings',()=>{
 const ring=[[0,0],[.0004,0],[.0004,.0003],[0,.0003],[0,0]]
 const building=[[.0005,.0001],[.0007,.0001],[.0007,.0003],[.0005,.0003],[.0005,.0001]]
 const neighbor=[[-.0003,-.0002],[.0002,-.0002],[.0002,-.00005],[-.0003,-.00005],[-.0003,-.0002]]
 const spots=areaSurroundSpots(ring,[.0002,.00015],[building,neighbor],{seed:7})
 assert.ok(spots.length>5)
 for(const p of spots){
  assert.ok(!inside(p,ring),'停在停车区内部')
  assert.ok(!inside(p,building),'停在楼内')
  assert.ok(!inside(p,neighbor),'停在其他停车区内')
  assert.ok(Math.hypot((p[0]-.0002)*111320,(p[1]-.00015)*111320)<=80+1e-6,'离停车区过远')
 }
 assert.deepEqual(spots,areaSurroundSpots(ring,[.0002,.00015],[building,neighbor],{seed:7}))
})

test('a parking ring fully enclosed by buildings yields no invented position',()=>{
 const ring=[[0,0],[.0002,0],[.0002,.0002],[0,.0002],[0,0]]
 const block=[[-.001,-.001],[.001,-.001],[.001,.001],[-.001,.001],[-.001,-.001]]
 assert.deepEqual(areaSurroundSpots(ring,[.0001,.0001],[block]),[])
 assert.deepEqual(areaSurroundSpots(null,[0,0],[block]),[])
})
