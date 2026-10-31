<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');

function respond(int $status, array $payload): void
{
    http_response_code($status);
    echo json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    header('Allow: POST');
    respond(405, ['ok' => false, 'error' => 'POST is required.']);
}

$length = (int) ($_SERVER['CONTENT_LENGTH'] ?? 0);
if ($length <= 0 || $length > 16384) {
    respond(413, ['ok' => false, 'error' => 'Message is too large.']);
}
$data = json_decode((string) file_get_contents('php://input'), true);
if (!is_array($data)) {
    respond(400, ['ok' => false, 'error' => 'Invalid request.']);
}
if (!empty($data['website'])) {
    respond(200, ['ok' => true]);
}

$name = trim(is_string($data['name'] ?? null) ? $data['name'] : '');
$email = trim(is_string($data['email'] ?? null) ? $data['email'] : '');
$topic = trim(is_string($data['topic'] ?? null) ? $data['topic'] : '');
$message = trim(is_string($data['message'] ?? null) ? $data['message'] : '');
$allowedTopics = ['Donate', 'Volunteer', 'Partner', 'General question'];
if ($name === '' || strlen($name) > 160 || strlen($email) > 254
    || !filter_var($email, FILTER_VALIDATE_EMAIL) || !in_array($topic, $allowedTopics, true)
    || $message === '' || strlen($message) > 10000) {
    respond(422, ['ok' => false, 'error' => 'Check the name, email, topic and message.']);
}

$to = getenv('AKADIWO_TO_EMAIL') ?: 'akadiwofoundation@gmail.com';
$from = getenv('AKADIWO_FROM_EMAIL') ?: '';
if (!filter_var($to, FILTER_VALIDATE_EMAIL) || !filter_var($from, FILTER_VALIDATE_EMAIL)) {
    respond(503, ['ok' => false, 'error' => 'The message service is not configured.']);
}

$subject = 'Website enquiry: ' . $topic;
$body = "Name: {$name}\nEmail: {$email}\nTopic: {$topic}\n\n{$message}";
$headers = [
    'MIME-Version: 1.0',
    'Content-Type: text/plain; charset=UTF-8',
    "From: Akadiwo website <{$from}>",
    "Reply-To: {$email}",
];
if (!mail($to, $subject, $body, implode("\r\n", $headers), '-f' . $from)) {
    respond(503, ['ok' => false, 'error' => 'The message could not be delivered.']);
}

respond(200, ['ok' => true]);
