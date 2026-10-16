import test from 'node:test'
import assert from 'node:assert/strict'
import {cleanPoints,polygonIssue} from '../src/annotationGeometry.js'

test('double click and returning to first vertex do not invalidate a rectangle',()=>{
 const points=[[0,0],[1,0],[1,0],[1,1],[0,1],[0,0],[0,0]]
 assert.deepEqual(cleanPoints(points),[[0,0],[1,0],[1,1],[0,1]])
 assert.equal(polygonIssue(points),'')
 assert.equal(points.length,7) // Do not mutate the original draft or saved region.
})
test('the user-reported failed shape remains valid after removing the repeated last click',()=>{
 const p=[[.33955044441677934,.6081021930435015],[.7048062921960965,.3854706379012907],[.6306790824994757,.2985383163695703],[.21042562752589142,.4734631096955931],[.33895264433858074,.6081021930435015],[.33895264433858074,.6081021930435015]]
 assert.equal(cleanPoints(p).length,5)
 assert.equal(polygonIssue(p),'')
})
test('crossing edges, degenerate regions and revisiting a nonadjacent vertex remain invalid',()=>{
 assert.match(polygonIssue([[0,0],[1,1],[0,1],[1,0]]),/交叉/)
 assert.match(polygonIssue([[0,0],[0,0],[1,1]]),/3个/)
 assert.match(polygonIssue([[0,0],[1,0],[.5,0]]),/面积/)
 assert.match(polygonIssue([[0,0],[1,0],[1,1],[1,0],[0,1]]),/重复/)
})
