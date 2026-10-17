import assert from 'node:assert/strict'
import test from 'node:test'
import {ScreenRoutes} from '../src/simulationRender.js'
class TestPath {moveTo(){} lineTo(){}}
test('screen route sampling projects each vertex once and shares partial geometry',()=>{const old=globalThis.Path2D;globalThis.Path2D=TestPath;try{let calls=0;const map={latLngToContainerPoint:([lat,lon])=>{calls++;return{x:lon*100,y:lat*100}}},routes=new ScreenRoutes(map,{p:{coordinates:[[0,0],[1,0],[2,0]]}});for(let i=0;i<1000;i++)assert.deepEqual(routes.sample('p',.5),{x:100,y:0});assert.equal(calls,3);assert.equal(routes.trace('p',.503),routes.trace('p',.509));routes.clear();routes.sample('p',.5);assert.equal(calls,6)}finally{globalThis.Path2D=old}})
