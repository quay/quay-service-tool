const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const YAML = require(path.join(__dirname, '../frontend/node_modules/yaml'));

function argument(name) {
  const index = process.argv.indexOf(name);
  if (index === -1 || !process.argv[index + 1]) {
    throw new Error(`${name} is required`);
  }
  return path.resolve(process.argv[index + 1]);
}

function writeAtomically(destination, content) {
  const temporary = `${destination}.tmp.${process.pid}`;
  fs.writeFileSync(temporary, content);
  fs.renameSync(temporary, destination);
}

const quayDir = argument('--quay-dir');
const sourcePath = argument('--artifact');
const artifactBytes = fs.readFileSync(sourcePath);
const artifact = JSON.parse(artifactBytes.toString('utf8'));
if (!artifact.version || typeof artifact.version !== 'string') {
  throw new Error('classifier artifact has no string version');
}

const sha256 = crypto.createHash('sha256').update(artifactBytes).digest('hex');
const stackDir = path.join(quayDir, 'local-dev/stack');
const destinationPath = path.join(stackDir, 'spam-classifier-demo.json');
if (sourcePath !== destinationPath) {
  const currentBytes = fs.existsSync(destinationPath) ? fs.readFileSync(destinationPath) : null;
  if (!currentBytes || !currentBytes.equals(artifactBytes)) {
    writeAtomically(destinationPath, artifactBytes);
  }
}

const configPath = path.join(stackDir, 'config.yaml');
const originalConfig = fs.readFileSync(configPath, 'utf8');
const document = YAML.parseDocument(originalConfig);
if (document.errors.length) {
  throw document.errors[0];
}
document.set('FEATURE_SPAM_DETECTION', true);
document.set('SPAM_DETECTION_DRY_RUN', false);
document.set('SPAM_DETECTION_FAIL_OPEN', false);
document.set('SPAM_DETECTION_CLASSIFIER_PATH', '/quay-registry/conf/stack/spam-classifier-demo.json');
document.set('SPAM_DETECTION_CLASSIFIER_VERSION', artifact.version);
document.set('SPAM_DETECTION_CLASSIFIER_SHA256', sha256);
const updatedConfig = String(document);
if (updatedConfig !== originalConfig) {
  writeAtomically(configPath, updatedConfig);
}

console.log(
  JSON.stringify({
    source: sourcePath,
    destination: destinationPath,
    version: artifact.version,
    sha256,
  }),
);
