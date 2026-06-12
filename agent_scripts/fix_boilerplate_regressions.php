<?php
/**
 * WIKI-BOILERPLATE-D: Fix 5 regressions + 4 RU Bambu AI articles
 *
 * Based on actual database state on 2026-06-12:
 * - Type A: "запросregarding your issue" (not English — already partially translated)
 *   Articles affected: 12155, 12177, 12737 (+1 extra found during audit)
 * - Type B: "please and </p>" — already cleaned, nothing to do
 * - 4 RU Bambu AI articles (10075, 10265, 10580, 11040) — already clean
 * - Additional Bambu AI articles found: 11017, 11288 (mention Bambu AI with /guides/ link)
 */
define('IBLOCK_ID', 60);
$db = new mysqli('localhost', 'bitrix0', 'lwtSNYi-8p?aCHkQR6-H', 'sitemanager');
if ($db->connect_error) die("DB connect failed\n");
$db->set_charset('utf8');
echo "=== WIKI-BOILERPLATE-D: Regression fix ===\n\n";

$stmt = $db->prepare("UPDATE b_iblock_element SET DETAIL_TEXT = ?, TIMESTAMP_X = NOW() WHERE ID = ?");

$updated = 0;
$skipped = 0;

// ==================================================================
// PART 1: Fix Type A — "запросregarding your issue" broken text
// ==================================================================
echo "--- Part 1: Type A (запросregarding your issue) ---\n";
$r = $db->query("SELECT ID, CODE, DETAIL_TEXT FROM b_iblock_element 
    WHERE IBLOCK_ID=60 AND DETAIL_TEXT LIKE '%запросregarding%'
    ORDER BY ID");
while ($row = $r->fetch_assoc()) {
    $id = (int)$row['ID'];
    $code = $row['CODE'];
    $text = $row['DETAIL_TEXT'];
    $orig = $text;

    // Pattern: Russian text with broken "запросregarding your issue</p>"
    // This is a <blockquote> End Notes boilerplate that was partially translated.
    // Fix 1: Remove the broken "regarding your issue" fragment from the Russian text
    $text = str_replace('запросregarding your issue', 'запрос.', $text);

    // Also fix any remaining variants
    $text = preg_replace('/запросregarding\s+your\s+issue/i', 'запрос.', $text);

    // Cleanup empty/invalid HTML artifacts
    do {
        $prev = $text;
        $text = preg_replace('~<a[^>]*>\s*</a>~i', '', $text);
        $text = preg_replace('~<(strong|em|i|b)>\s*</\1>~i', '', $text);
        $text = preg_replace('~<p>\s*(?:<br\s*/?>)?\s*</p>~i', '', $text);
        $text = preg_replace('/ {2,}/', ' ', $text);
        $text = preg_replace("/\n{3,}/", "\n\n", $text);
    } while ($text !== $prev);
    
    $text = trim($text);

    if ($text === $orig) {
        echo "  ID $id ($code): no match, skipping\n";
        $skipped++;
        continue;
    }
    $stmt->bind_param('si', $text, $id);
    if ($stmt->execute()) {
        echo "  ID $id ($code): fixed ✅\n";
        $updated++;
    }
}

// ==================================================================
// PART 2: Remove RU-translated Bambu AI blocks
// ==================================================================
echo "\n--- Part 2: RU-translated Bambu AI blocks ---\n";
$r = $db->query("SELECT ID, CODE, DETAIL_TEXT FROM b_iblock_element 
    WHERE IBLOCK_ID=60 AND DETAIL_TEXT LIKE '%Bambu AI%'
    ORDER BY ID");
while ($row = $r->fetch_assoc()) {
    $id = (int)$row['ID'];
    $code = $row['CODE'];
    $text = $row['DETAIL_TEXT'];
    $orig = $text;

    // Remove <p> blocks containing "Bambu AI" (allow nested HTML tags)
    // Uses (?:(?!</p>).)* to match any char that doesn't start </p>
    $text = preg_replace(
        '~<p>(?:(?!</p>).)*Bambu AI(?:(?!</p>).)*</p>~is',
        '',
        $text
    );

    // Remove <blockquote> blocks containing "Bambu AI" (allow nested HTML)
    $text = preg_replace(
        '~<blockquote>(?:(?!</blockquote>).)*Bambu AI(?:(?!</blockquote>).)*</blockquote>~is',
        '',
        $text
    );

    // Cleanup empty HTML
    do {
        $prev = $text;
        $text = preg_replace('~<a[^>]*>\s*</a>~i', '', $text);
        $text = preg_replace('~<(strong|em|i|b)>\s*</\1>~i', '', $text);
        $text = preg_replace('~<p>\s*(?:<br\s*/?>)?\s*</p>~i', '', $text);
        $text = preg_replace('~<blockquote>\s*(?:<br\s*/?>\s*)?(?:<p>\s*</p>\s*)?</blockquote>~i', '', $text);
        $text = preg_replace('/ {2,}/', ' ', $text);
        $text = preg_replace("/\n{3,}/", "\n\n", $text);
    } while ($text !== $prev);
    
    $text = trim($text);

    if ($text === $orig) {
        echo "  ID $id ($code): no match, skipping\n";
        $skipped++;
        continue;
    }
    $stmt->bind_param('si', $text, $id);
    if ($stmt->execute()) {
        echo "  ID $id ($code): fixed ✅\n";
        $updated++;
    }
}

echo "\n=== RESULT ===\n";
echo "Updated: $updated\nSkipped: $skipped\n";

// Verification
echo "\n=== VERIFICATION ===\n";
$fail = 0;

$r2 = $db->query("SELECT COUNT(*) as c FROM b_iblock_element WHERE IBLOCK_ID=60 AND DETAIL_TEXT LIKE '%запросregarding%'");
$c = (int)$r2->fetch_assoc()['c'];
if ($c > 0) { echo "  'запросregarding': $c remaining ❌\n"; $fail += $c; }
else { echo "  'запросregarding': 0 ✅\n"; }

$r2 = $db->query("SELECT COUNT(*) as c FROM b_iblock_element WHERE IBLOCK_ID=60 AND DETAIL_TEXT LIKE '%Bambu AI%'");
$c = (int)$r2->fetch_assoc()['c'];
if ($c > 0) { echo "  'Bambu AI': $c remaining ❌\n"; $fail += $c; }
else { echo "  'Bambu AI': 0 ✅\n"; }

if ($fail === 0) echo "\nSUCCESS! All fixes applied. 🎉\n";
else echo "\nWARNING: $fail remaining items need review.\n";