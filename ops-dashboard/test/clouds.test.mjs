import test from 'node:test'
import assert from 'node:assert/strict'
import { normalizeDockerOutput, normalizeGcpServices } from '../src/clouds.mjs'

test('SSH docker ps/stats output groups containers by host and maps Compose roles', () => {
  const ps = [
    { ID: 'a1b2', Names: 'simpleword-api-1', Image: 'simple-word:v2', State: 'running', Status: 'Up 2 minutes (healthy)', Labels: 'com.docker.compose.project=simpleword,com.docker.compose.service=api' },
    { ID: 'c3d4', Names: 'simpleword-proxy-1', Image: 'simple-word-proxy:latest', State: 'running', Status: 'Up 2 minutes (healthy)', Labels: 'com.docker.compose.project=simpleword,com.docker.compose.service=proxy' },
    { ID: 'e5f6', Names: 'simpleword-canary-1', Image: 'simple-word:canary', State: 'running', Status: 'Up 2 minutes (healthy)', Labels: 'com.docker.compose.project=simpleword,com.docker.compose.service=canary' },
  ].map(JSON.stringify).join('\n')
  const stats = [
    { Container: 'a1b2', CPUPerc: '12.50%', MemPerc: '33.00%' },
    { Container: 'c3d4', CPUPerc: '1.00%', MemPerc: '10.00%' },
    { Container: 'e5f6', CPUPerc: '3.00%', MemPerc: '12.00%' },
  ].map(JSON.stringify).join('\n')
  const [host] = normalizeDockerOutput(ps, stats, 'lightsail-1')
  assert.equal(host.name, 'lightsail-1')
  assert.deepEqual(host.services[0].containers.map(({ role }) => role), ['api', 'proxy', 'canary'])
  assert.equal(host.services[0].containers[0].image, 'simple-word:v2')
  assert.equal(host.services[0].containers[0].health, 'healthy')
  assert.equal(host.services[0].containers[0].cpu, '12.50%')
  assert.equal(host.services[0].containers[0].memory, '33.00%')
})

test('Cloud Run output normalizes revisions, traffic, roles, resources, and scaling', () => {
  const serviceName = 'simple-word'
  const services = [{ metadata: { name: serviceName, labels: { 'cloud.googleapis.com/location': 'asia-northeast3' } } }]
  const revisions = [
    ['simple-word-00003-abc', 'simple-word:v3', 'True'],
    ['simple-word-canary-00001-def', 'simple-word:canary', 'True'],
    ['simple-word-shadow-00001-ghi', 'simple-word:shadow', 'False'],
  ].map(([name, image, ready]) => ({ metadata: { name, creationTimestamp: '2026-11-19T00:00:00Z' }, spec: { containers: [{ image }] }, status: { conditions: [{ type: 'Ready', status: ready }] } }))
  const details = {
    [serviceName]: {
      spec: { template: { metadata: { annotations: { 'autoscaling.knative.dev/minScale': '1', 'autoscaling.knative.dev/maxScale': '8' } } } },
      status: {
        url: 'https://simple-word.example.run.app',
        conditions: [{ type: 'Ready', status: 'True' }],
        traffic: [
          { revisionName: 'simple-word-00003-abc', percent: 80 },
          { revisionName: 'simple-word-canary-00001-def', percent: 10 },
          { revisionName: 'simple-word-shadow-00001-ghi', percent: 10 },
        ],
      },
    },
  }
  const metrics = {
    [serviceName]: {
      instanceCount: revisions.map((revision, index) => ({ resource: { labels: { revision_name: revision.metadata.name } }, points: [{ value: { int64Value: String(index + 1) } }] })),
      cpuUtilization: revisions.map((revision, index) => ({ resource: { labels: { revision_name: revision.metadata.name } }, points: [{ value: { doubleValue: [.25, .5, .75][index] } }] })),
      memoryUtilization: revisions.map((revision, index) => ({ resource: { labels: { revision_name: revision.metadata.name } }, points: [{ value: { doubleValue: [.3, .4, .6][index] } }] })),
    },
  }
  const [result] = normalizeGcpServices(services, details, { [serviceName]: revisions }, metrics, 'asia-northeast3')
  assert.equal(result.minInstances, 1)
  assert.equal(result.maxInstances, 8)
  assert.equal(result.ready, true)
  assert.equal(result.revisions[0].image, 'simple-word:v3')
  assert.equal(result.revisions[0].createdAt, '2026-11-19T00:00:00Z')
  assert.equal(result.revisions[2].ready, false)
  assert.equal(result.revisions.reduce((sum, row) => sum + row.trafficPercent, 0), 100)
  assert.deepEqual(result.revisions.map(({ role }) => role), ['service', 'canary', 'shadow'])
  assert.equal(result.revisions[1].instances, 2)
  assert.equal(result.revisions[0].cpuUtilization, 25)
  assert.equal(result.revisions[0].memoryUtilization, 30)
})
