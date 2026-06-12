<?php
/**
 * WIKI-BOILERPLATE-B: Remove English boilerplate - V7 ROBUST
 *
 * Uses regex to handle HTML-split text (e.g. <em>please submit a <a>technical ticket</a></em>).
 * Finds entire <blockquote> that contain boilerplate text and removes them.
 * Also handles standalone boilerplate <p> inside safety blockquotes.
 */
define('IBLOCK_ID', 60);
$db = new mysqli('localhost', 'bitrix0', 'lwtSNYi-8p?aCHkQR6-H', 'sitemanager');
if ($db->connect_error) die("DB connect failed\n");
$db->set_charset('utf8');
echo "=== V7: Robust regex pass ===\n\n";

// Select ANY article with residual boilerplate signals
$where = "IBLOCK_ID=60 AND (
  DETAIL_TEXT LIKE '%We will do our best%' 
  OR DETAIL_TEXT LIKE '%We hope%' 
  OR DETAIL_TEXT LIKE '%support ticket%' 
  OR DETAIL_TEXT LIKE '%Support Ticket%' 
  OR DETAIL_TEXT LIKE '%customer service%' 
  OR DETAIL_TEXT LIKE '%open a new ticket%' 
  OR DETAIL_TEXT LIKE '%Click here%' 
  OR DETAIL_TEXT LIKE '%encourage you%' 
  OR DETAIL_TEXT LIKE '%technical support%' 
  OR DETAIL_TEXT LIKE '%technical ticket%' 
  OR DETAIL_TEXT LIKE '%Please contact our%' 
  OR DETAIL_TEXT LIKE '%for further assistance%' 
  OR DETAIL_TEXT LIKE '%review your request%' 
  OR DETAIL_TEXT LIKE '%Our team is always%' 
  OR DETAIL_TEXT LIKE '%we will answer your questions%'
  OR DETAIL_TEXT LIKE '%we will answer your%'
  OR DETAIL_TEXT LIKE '%submit a technical ticket%'
  OR DETAIL_TEXT LIKE '%if this guide does not solve%'
)";

$r = $db->query("SELECT COUNT(*) as cnt FROM b_iblock_element WHERE $where");
echo "Articles: " . (int)$r->fetch_assoc()['cnt'] . "\n";

$r = $db->query("SELECT ID, CODE, DETAIL_TEXT FROM b_iblock_element WHERE $where ORDER BY ID");

$updated = 0;
$skipped = 0;
$stmt = $db->prepare("UPDATE b_iblock_element SET DETAIL_TEXT = ?, TIMESTAMP_X = NOW() WHERE ID = ?");

// Regex patterns to remove entire <blockquote> blocks that contain boilerplate
// Strategy: strip HTML tags to check if the blockquote's text content matches boilerplate
$bqPatterns = [
    // 1. <blockquote> containing "if this guide does not solve your problem" or "We hope" + "provide assistance"
    '~<blockquote>(?:(?!</blockquote>).)*?(?:If this guide does not solve your problem|We hope[^<]*?was helpful|We hope that the detailed guide|We hope this guide has provided clear).*?</blockquote>~is',
    
    // 2. <blockquote> containing support ticket pattern
    '~<blockquote>(?:(?!</blockquote>).)*?(?:please submit a .{0,50}?(?:support ticket|Support Ticket|technical ticket).{0,200}?(?:review your request|we will answer your questions|provide detailed assistance)).*?</blockquote>~is',
    
    // 3. <blockquote> containing customer service / contact patterns
    '~<blockquote>(?:(?!</blockquote>).)*?(?:please contact (?:our|the) customer service team for further assistance).*?</blockquote>~is',
    
    // 4. <blockquote> containing open a new ticket for assistance
    '~<blockquote>(?:(?!</blockquote>).)*?(?:open a new ticket in our Support Page for assistance|new ticket in our Support Page for assistance).*?</blockquote>~is',
    
    // 5. <blockquote> with "We hope our guide was helpful" + "contact our customer service team"
    '~<blockquote>(?:(?!</blockquote>).)*?(?:We hope our guide was helpful).{0,300}?(?:contact our customer service team).*?</blockquote>~is',
];

// Also handle inline boilerplate <p> that might be inside a safety blockquote  
$inlinePatterns = [
    // Remove <p> containing "Click here to open a new ticket" with optional link
    '~<p>(?:<[^>]+>\s*)*[^<]{0,100}?(?:Click here to open a new ticket in our Support Page|open a new ticket in our Support Page for assistance)(?:<[^>]+>\s*)*[^<]*?</p>~is',
    
    // Remove <p> with "we will do our best to respond promptly"
    '~<p>(?:<[^>]+>\s*)*[^<]{0,50}?We will do our best to respond promptly[^<]*?</p>~is',
    
    // Remove <p> with "we will do our best to respond promptly" (lowercase)
    '~<p>(?:<[^>]+>\s*)*[^<]{0,50}?we will do our best to respond promptly[^<]*?</p>~is',
    
    // Remove <p> with "encourage you to reach out to our friendly customer service"
    '~<p>(?:<[^>]+>\s*)*[^<]{0,50}?encourage you to reach out to our friendly customer service[^<]*?</p>~is',
    
    // Remove <p> that contains "We hope..." variants 
    '~<p>(?:<[^>]+>\s*)*[^<]{0,20}?We hope (?:that )?(?:this guide|our guide|the detailed guide)[^<]*?</p>~is',
    
    // Remove standalone "we will answer your questions" (can be inside other tags)
    '~<p>(?:<[^>]+>\s*)*[^<]{0,100}?we will answer your questions[^<]*?</p>~is',
];

while ($row = $r->fetch_assoc()) {
    $id = (int)$row['ID'];
    $code = $row['CODE'];
    $text = $row['DETAIL_TEXT'];
    $orig = $text;

    // Apply blockquote patterns (remove entire blockquotes)
    foreach ($bqPatterns as $pat) {
        $text = preg_replace($pat, '', $text);
    }
    
    // Apply inline patterns (remove specific <p>)
    foreach ($inlinePatterns as $pat) {
        $text = preg_replace($pat, '', $text);
    }

    // Apply text-only patterns for leftovers (str_ireplace for non-HTML-split text)
    $phrases = [
        "If this guide does not solve your problem, please submit a technical ticket, we will answer your questions and provide assistance.",
        "If this guide does not solve your problem, please submit a technical ticket, we will answer your questions and provide assistance",
        "if this guide does not solve your problem, ",
        "If this guide does not solve your problem, ",
        "We hope that the detailed guide we shared with you was helpful and informative.",
        "We hope that the detailed guide we shared with you was helpful and informative",
        "We hope that the detailed guide was helpful and informative.",
        "We hope that the detailed guide",
        "We will do our best to respond promptly",
        "we will do our best to respond promptly",
        "and we will do our best to respond promptly",
        "Click here to open a new ticket in our Support Page",
        "open a new ticket in our Support Page",
        "new ticket in our Support Page for assistance",
        "Please contact our customer service team",
        "Please contact the customer service team for further assistance",
        "please contact the customer service team for further assistance",
        "our friendly customer service team",
        "Our team is always ready to help you and answer any questions you may have.",
        "our team is always ready to help you and answer any questions you may have",
        "We encourage you to reach out to",
        "we encourage you to reach out to",
        "encourage you to reach out to",
        "We hope our guide was helpful",
        "we hope our guide was helpful",
        "We hope this guide was helpful",
        "We hope this guide has been helpful",
        "We hope the detailed guide provided has been helpful",
        "We're here to assist you.",
        "We are here to assist you.",
        "Please submit a Support Ticket.",
        "please submit a support ticket",
        "Please submit a support ticket",
        "please submit a Support Ticket.",
        "our technical team will review your request",
        "Our technical team will review your request",
        "review your request and provide detailed assistance",
        // Leftover fragments after partial removal
        "we will answer your questions and provide assistance",
        "we will answer your questions and provide assistance.",
        "we will answer your questions",
        ", we will answer your questions and provide assistance",
        "please submit a",
        "please submit a technical ticket",
        "and include your recent printer logs and additional pictures or other details",
        "include your recent printer logs and additional pictures or other details",
        "Supply a support ticket",
    ];
    foreach ($phrases as $p) {
        $text = str_ireplace($p, '', $text);
    }

    // Cleanup empty/invalid HTML
    do {
        $prev = $text;
        $text = preg_replace('~<a[^>]*>\s*</a>~i', '', $text);
        $text = preg_replace('~<(i|em)>\s*</\\1>~i', '', $text);
        $text = preg_replace('~<p>\s*(?:<br\s*/?>\s*)*</p>~i', '', $text);
        $text = preg_replace('~<p>\s*</p>~i', '', $text);
        $text = preg_replace('~<blockquote>\s*(?:<br\s*/?>\s*)*</blockquote>~i', '', $text);
        $text = preg_replace('~<blockquote>\s*<p>\s*</p>\s*</blockquote>~i', '', $text);
        $text = preg_replace('~<blockquote>\s*</blockquote>~i', '', $text);
        $text = preg_replace('~<blockquote>\s*(?:<br\s*/?>\s*)*<p>\s*</p>\s*</blockquote>~i', '', $text);
        $text = preg_replace('~<p>\s*<br\s*/?>\s*</p>~i', '', $text);
        $text = preg_replace('~<a\s[^>]*href="[^"]*"[^>]*>\s*/guides/\s*</a>~i', '', $text);
        // Remove dangling commas, periods at end of <p>
        $text = preg_replace('~,\s*</p>~i', '</p>', $text);
        $text = preg_replace('~\.\.\s*</p>~i', '.</p>', $text);
    } while ($text !== $prev);
    
    $text = preg_replace('/ {2,}/', ' ', $text);
    $text = preg_replace("/\n{3,}/", "\n\n", $text);
    $text = trim($text);
    
    if ($text === $orig) { $skipped++; continue; }
    $stmt->bind_param('si', $text, $id);
    if ($stmt->execute()) $updated++;
}

echo "Updated: $updated\nSkipped: $skipped\n";

echo "\n=== FINAL VERIFICATION ===\n";
$patterns = [
    "If this guide does not solve your problem",
    "We hope that the detailed guide",
    "We hope our guide was helpful",
    "We hope this guide has provided",
    "We will do our best to respond promptly",
    "Click here to open a new ticket",
    "open a new ticket in our Support",
    "Please contact our customer",
    "customer service team for further assistance",
    "please submit a support ticket",
    "Please submit a Support Ticket",
    "please submit a",
    "encourage you to reach out",
    "Our team is always ready to help",
    "review your request",
    "we will answer your questions",
    "technical support team",
];
$remaining = 0;
foreach ($patterns as $pat) {
    $esc = $db->real_escape_string($pat);
    $r2 = $db->query("SELECT COUNT(*) as c FROM b_iblock_element WHERE IBLOCK_ID=60 AND DETAIL_TEXT LIKE '%$esc%'");
    $c = (int)$r2->fetch_assoc()['c'];
    if ($c > 0) { echo "  '$pat': $c\n"; $remaining += $c; }
}
echo "Total remaining: $remaining\n";
if ($remaining === 0) echo "SUCCESS!\n";