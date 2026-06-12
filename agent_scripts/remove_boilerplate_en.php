<?php
/**
 * WIKI-BOILERPLATE-B: Remove English boilerplate from 96 articles
 *
 * Task: After replacing bambulab.com/en/support links with /guides/ in 120 articles,
 * English boilerplate support text remains. This script removes it.
 *
 * Patterns removed:
 * 1. "We will do our best to respond promptly and provide the assistance you need."
 * 2. "Click here to open a new ticket in our Support Page"
 * 3. "Please contact our customer service team"
 * 4. "We hope our guide was helpful"
 * 5. "...encourage you to reach out to our friendly customer service team..."
 *
 * All boilerplate sits inside <blockquote> after <h2>End Notes</h2> sections.
 * After removing boilerplate <p> blocks, empties the <blockquote> entirely.
 *
 * IBLOCK_ID=60 (wiki-guides) on 1-sloy.ru, DB sitemanager
 *
 * Usage: ssh -T 1sloy php /path/to/remove_boilerplate_en.php
 */

define('IBLOCK_ID', 60);

$db = new mysqli('localhost', 'bitrix0', 'lwtSNYi-8p?aCHkQR6-H', 'sitemanager');
if ($db->connect_error) {
    die("DB connect failed: {$db->connect_error}\n");
}
$db->set_charset('utf8');

echo "=== WIKI-BOILERPLATE-B: English boilerplate removal ===\n\n";

// Step 1: Count affected
$result = $db->query("
    SELECT COUNT(*) as cnt
    FROM b_iblock_element
    WHERE IBLOCK_ID = " . IBLOCK_ID . "
      AND (DETAIL_TEXT LIKE '%We will do our best to respond promptly%'
        OR DETAIL_TEXT LIKE '%Click here to open a new ticket in our Support Page%'
        OR DETAIL_TEXT LIKE '%Please contact our customer service team%'
        OR DETAIL_TEXT LIKE '%We hope our guide was helpful%'
        OR DETAIL_TEXT LIKE '%encourage you to reach out%')
");
$row = $result->fetch_assoc();
$totalBefore = (int)$row['cnt'];
echo "Articles with boilerplate: $totalBefore\n";

if ($totalBefore === 0) {
    echo "Nothing to do.\n";
    exit(0);
}

// Step 2: Select affected articles with IDs
$result = $db->query("
    SELECT ID, CODE, DETAIL_TEXT
    FROM b_iblock_element
    WHERE IBLOCK_ID = " . IBLOCK_ID . "
      AND (DETAIL_TEXT LIKE '%We will do our best to respond promptly%'
        OR DETAIL_TEXT LIKE '%Click here to open a new ticket in our Support Page%'
        OR DETAIL_TEXT LIKE '%Please contact our customer service team%'
        OR DETAIL_TEXT LIKE '%We hope our guide was helpful%'
        OR DETAIL_TEXT LIKE '%encourage you to reach out%')
    ORDER BY ID
");

$updated = 0;
$skipped = 0;
$errors = [];
$stmt = $db->prepare("UPDATE b_iblock_element SET DETAIL_TEXT = ?, TIMESTAMP_X = NOW() WHERE ID = ?");

while ($row = $result->fetch_assoc()) {
    $id = (int)$row['ID'];
    $code = $row['CODE'];
    $text = $row['DETAIL_TEXT'];
    $original = $text;

    // --- STEP 1: Remove the ENTIRE boilerplate blockquote after End Notes ---
    // Match <blockquote> that contains any of the boilerplate markers and remove it entirely
    $patterns = [
        // Pattern A: <blockquote><p>We hope our guide was helpful...</p> ... <p>We will do our best...</p></blockquote>
        // Pattern B: <blockquote><p>...encourage you to reach out...</p> ... <p>We will do our best...</p></blockquote>
        '~<blockquote>\s*<p>[^<]*?(?:We hope our guide was helpful|encourage you to reach out)[^<]*</p>\s*(?:<p>[^<]*</p>\s*)*<p>[^<]*?We will do our best to respond promptly[^<]*</p>\s*</blockquote>~is',
        
        // Pattern C: <blockquote> with only We will do our best... (no first paragraph)
        '~<blockquote>\s*<p>[^<]*?We will do our best to respond promptly[^<]*</p>\s*</blockquote>~is',
    ];

    $text = preg_replace($patterns, '', $text, -1, $count);

    // --- STEP 2: Clean up any remaining orphan boilerplate paragraphs outside blockquotes ---
    $orphanPatterns = [
        '~<p>[^<]*?We will do our best to respond promptly[^<]*</p>\s*~is',
        '~<p>[^<]*?Click here to open a new ticket in our Support Page[^<]*</p>\s*~is',
        '~<p>[^<]*?Please contact our customer service team[^<]*</p>\s*~is',
        '~<p>[^<]*?We hope our guide was helpful[^<]*</p>\s*~is',
        '~<p>[^<]*?encourage you to reach out[^<]*</p>\s*~is',
    ];
    foreach ($orphanPatterns as $pat) {
        $text = preg_replace($pat, '', $text, -1);
    }

    // --- STEP 3: Remove empty blockquotes left behind ---
    $text = preg_replace('~<blockquote>\s*</blockquote>\s*~is', '', $text);
    $text = preg_replace('~<blockquote>\s*</blockquote>~is', '', $text);

    // --- STEP 4: Clean up double newlines/whitespace ---
    $text = preg_replace('~\n{3,}~', "\n\n", $text);

    $text = trim($text);

    if ($text === $original) {
        $skipped++;
        continue;
    }

    $stmt->bind_param('si', $text, $id);
    if ($stmt->execute()) {
        $updated++;
        echo "  Updated: ID=$id ($code)\n";
    } else {
        $errors[] = "ID=$id ($code): {$stmt->error}";
    }
}

echo "\n=== Results ===\n";
echo "Total affected before: $totalBefore\n";
echo "Updated: $updated\n";
echo "Skipped (no change): $skipped\n";
if (!empty($errors)) {
    echo "Errors: " . count($errors) . "\n";
    foreach ($errors as $e) echo "  $e\n";
}

// Step 3: Verify - count remaining
$result = $db->query("
    SELECT COUNT(*) as cnt
    FROM b_iblock_element
    WHERE IBLOCK_ID = " . IBLOCK_ID . "
      AND (DETAIL_TEXT LIKE '%We will do our best to respond promptly%'
        OR DETAIL_TEXT LIKE '%Click here to open a new ticket in our Support Page%'
        OR DETAIL_TEXT LIKE '%Please contact our customer service team%'
        OR DETAIL_TEXT LIKE '%We hope our guide was helpful%'
        OR DETAIL_TEXT LIKE '%encourage you to reach out%')
");
$row = $result->fetch_assoc();
$remaining = (int)$row['cnt'];

echo "Remaining articles with boilerplate: $remaining\n";

if ($remaining === 0) {
    echo "\nSUCCESS: All boilerplate removed.\n";
} else {
    echo "\nWARNING: $remaining articles still have boilerplate.\n";
}