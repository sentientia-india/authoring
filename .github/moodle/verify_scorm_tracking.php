<?php
// Verify persisted LMS records after the browser import/relaunch scenarios.
define('CLI_SCRIPT', true);
require(__DIR__ . '/config.php');

$student = $DB->get_record('user', ['username' => 'student1'], '*', MUST_EXIST);
$requirements = [
    'Course MCP SCORM 1.2' => [
        'location' => ['cmi.core.lesson_location', 'acceptance-complete'],
        'suspend' => ['cmi.suspend_data', 'course-mcp-moodle'],
        'score' => ['cmi.core.score.raw', '100'],
        'completion' => ['cmi.core.lesson_status', 'passed'],
        'session_time' => ['cmi.core.session_time', null],
        'interaction' => ['cmi.interactions.0.id', 'final-check'],
    ],
    'Course MCP SCORM 2004' => [
        'location' => ['cmi.location', 'acceptance-complete'],
        'suspend' => ['cmi.suspend_data', 'course-mcp-moodle'],
        'score' => ['cmi.score.raw', '100'],
        'completion' => ['cmi.completion_status', 'completed'],
        'success' => ['cmi.success_status', 'passed'],
        'session_time' => ['cmi.session_time', null],
        'interaction' => ['cmi.interactions.0.id', 'final-check'],
    ],
];

$evidence = [
    'moodle_release' => $CFG->release,
    'moodle_version' => $CFG->version,
    'verified_at_utc' => gmdate('c'),
    'packages' => [],
];

foreach ($requirements as $name => $checks) {
    $scorm = $DB->get_record('scorm', ['name' => $name], '*', MUST_EXIST);
    $records = $DB->get_records('scorm_scoes_track', [
        'userid' => $student->id,
        'scormid' => $scorm->id,
    ]);
    $tracks = [];
    foreach ($records as $record) {
        $tracks[$record->element] = $record->value;
    }
    foreach ($checks as $capability => [$element, $expected]) {
        if (!array_key_exists($element, $tracks)) {
            throw new RuntimeException("{$name}: missing {$element} for {$capability}");
        }
        $actual = (string)$tracks[$element];
        if ($expected !== null && strpos($actual, $expected) === false) {
            throw new RuntimeException("{$name}: {$element} expected {$expected}, got {$actual}");
        }
        if ($capability === 'session_time' && ($actual === '' || $actual === '00:00:00' || $actual === 'PT0H0M0S')) {
            throw new RuntimeException("{$name}: session time was not greater than zero");
        }
    }
    $evidence['packages'][] = [
        'name' => $name,
        'scorm_id' => (int)$scorm->id,
        'attempt' => max(array_map(static fn($record) => (int)$record->attempt, $records)),
        'verified_capabilities' => array_keys($checks),
        'tracks' => array_intersect_key($tracks, array_flip(array_column($checks, 0))),
    ];
}

$output = json_encode($evidence, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
if ($output === false) {
    throw new RuntimeException('Unable to encode Moodle evidence.');
}
file_put_contents('/tmp/course-mcp-moodle-tracking.json', $output . PHP_EOL);
echo $output . PHP_EOL;
