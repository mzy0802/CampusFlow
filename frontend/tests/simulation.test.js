import assert from 'node:assert/strict'
import test from 'node:test'
import {routePoint,phase,occupancy,inside,arrivalTime,parkingTotals,parkingLabelPoint,zoneDetailsAt} from '../src/simulationMath.js'
test('distance interpolation follows bends instead of taking a shortcut',()=>{const p=[[0,0],[0,1],[1,1]];const v=routePoint(p,.25);assert.equal(v[0],0);assert.ok(v[1]>.49&&v[1]<.51)})
test('zero length route stays finite',()=>assert.deepEqual(routePoint([[1,2],[1,2]],.6),[1,2]))
test('rider parks then appears beside vehicle and walks continuously',()=>{const a={id:1,mode:'bicycle',area_id:'lot',start:10,travel_seconds:20,path:'ride',walk_path:'walk'},paths={walk:{seconds:50}};assert.equal(phase(a,0,paths).kind,'waiting');assert.equal(phase(a,15,paths).kind,'moving');assert.equal(phase(a,31,paths).kind,'parking');assert.equal(phase(a,49,paths).kind,'dismount');assert.equal(phase(a,68,paths).kind,'leaving');assert.equal(phase(a,100,paths).kind,'walking');assert.equal(phase(a,160,paths).kind,'arrived');assert.deepEqual(occupancy([a],80,8),{lot:8});assert.deepEqual(occupancy([a],40,8),{})})
test('phase boundaries do not skip or double count a parked vehicle',()=>{const a={id:2,mode:'electric',area_id:'lot',start:0,travel_seconds:10,walk_path:'walk'},paths={walk:{seconds:30}};assert.equal(phase(a,27.99,paths).kind,'parking');assert.equal(phase(a,28,paths).kind,'dismount');assert.equal(phase(a,46,paths).kind,'leaving');assert.equal(phase(a,70,paths).kind,'walking');assert.deepEqual(occupancy([a],28,2),{lot:2});assert.deepEqual(occupancy([a],100,2),{lot:2});assert.equal(phase(a,100,paths).kind,'entering');assert.equal(phase(a,112,paths).kind,'arrived')})
test('parked glyphs can be restricted to actual polygon',()=>{assert.ok(inside([.5,.5],[[0,0],[1,0],[1,1],[0,1],[0,0]]));assert.equal(inside([2,2],[[0,0],[1,0],[1,1],[0,1],[0,0]]),false)})

test('full route is retained until arrival and the retention interval uses final building entry',()=>{const a={start:20,mode:'bike',travel_seconds:100,walk_path:'p'};assert.equal(arrivalTime(a,{p:{seconds:40}}),232);assert.equal(arrivalTime({start:10,mode:'walk',travel_seconds:60},{}),82)})
test('illegal vehicles are a subset of occupancy, not added to it',()=>{const agents=[{start:0,travel_seconds:10,area_id:'p',illegal:true},{start:0,travel_seconds:10,area_id:'p',illegal:false}];assert.deepEqual(parkingTotals(agents,30,4),{loads:{p:8},illegal:{p:4}});assert.deepEqual(parkingTotals(agents,20,4),{loads:{},illegal:{}})})
test('labels shrink when zoomed out and clear the parking polygon at close zoom',()=>{const ring=[{x:100,y:100},{x:200,y:100},{x:200,y:200},{x:100,y:200}];const far=parkingLabelPoint(ring,14),near=parkingLabelPoint(ring,19);assert.ok(far.scale<near.scale);assert.equal(far.outside,false);assert.equal(near.outside,true);assert.ok(near.y+17*near.scale<100)})

test('variable speed profiles stay synchronized through meal and walking legs',()=>{
 const a={id:1,mode:'bicycle',area_id:'lot',start:100,travel_seconds:420,path:'p',via_path:'v',leg1_seconds:60,dwell_seconds:240,leg1_pace:[[0,0],[30,.2],[60,1]],travel_pace:[[0,0],[60,.25],[120,1]],walk_path:'w',walk_seconds:120,walk_pace:[[0,0],[60,.2],[120,1]]},paths={w:{seconds:120}}
 assert.equal(phase(a,130,paths).progress,.2)
 assert.equal(phase(a,250,paths).kind,'dining')
 assert.equal(phase(a,460,paths).progress,.25)
 assert.equal(phase(a,640,paths).progress,.2)
})
test('parking congestion delays occupancy without counting a vehicle twice',()=>{
 const a={id:1,mode:'bicycle',area_id:'lot',start:0,travel_seconds:100,parking_seconds:78,walk_path:'w',walk_seconds:40},paths={w:{seconds:40}}
 assert.equal(phase(a,160,paths).kind,'parking')
 assert.deepEqual(parkingTotals([a],160,1).loads,{})
 assert.deepEqual(parkingTotals([a],178,1).loads,{lot:1})
 assert.equal(phase(a,196,paths).kind,'leaving')
 assert.equal(phase(a,220,paths).kind,'walking')
 assert.equal(arrivalTime(a,paths),272)
})
test('source/destination counts remain exact between timeline buckets and during meals',()=>{
 const people=[
  {mode:'walk',start:0,travel_seconds:1000,destination_name:'修远一区'},
  {mode:'walk',start:100,travel_seconds:1000,destination_name:'修远一区',board_at:'食堂'},
  {mode:'walk',start:100,travel_seconds:600,destination_name:'明远A栋',via_path:'v',leg1_seconds:60,dwell_seconds:240},
  {mode:'walk',start:0,travel_seconds:900,destination_name:'鸿远一区',via_path:'v',leg1_seconds:200,dwell_seconds:300},
  {mode:'walk',start:0,travel_seconds:100,destination_name:'鸿远一区'}
 ]
 const z=zoneDetailsAt(people,450,{})
 assert.equal(z['修远'].active,2);assert.equal(z['修远'].dorm_source,1);assert.equal(z['修远'].canteen_source,1)
 assert.equal(z['明远'].canteen_source,1)
 assert.equal(z['食堂'].active,1);assert.equal(z['食堂'].outgoing,1)
 assert.equal(z['鸿远'].active,0);assert.equal(z['鸿远'].arrived,1)
})
