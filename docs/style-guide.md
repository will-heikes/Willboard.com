# Willboard Style Guide

This guide covers all Willboard writing: the weekly chart recap, Chart Beat articles, awards predictions, and Pop Week. The model is Will's own writing. That means his weekly chart write-ups (the "Chart NNN" docs in the Drive `Charts` folder, 2015–2016) and his blog, [My Country Truth](https://mycountrytruth.blogspot.com/) ("I'm not afraid to say it how it is").

When this guide and an instruction from Will disagree, Will wins. Add his correction here.

---

## 1. Voice

- **Reporter first, fan second.** Will writes like a chart columnist who loves the music. He reports the facts, then adds the bit of trivia that makes the move matter. Opinions are blunt and short ("Just give it to Luke, he deserves it!"). They are never mean, and he never hedges.
- **Perspective over adjectives.** Make a move matter with a comparison, not a superlative. Will writes "the most since the week of September 24, when Toby Keith held #1 for a third week with ’35 Mph Town’" where others would write "a huge week".
- **Signature transitions.** Use them, but don't overuse any single one in a piece: "Underneath X is…", "Just below…", "Just outside the Top 5…", "Rounding out the Top 5/Top 10…", "New to the Top 5…", "Interestingly,", "In fact,", "To put this in perspective,", "In other news,", "Over on the Pop 10,".
- **A wink is allowed.** "Is this an omen for ‘Amen?’ We'll find out in three weeks!" Keep it to one per piece.
- **No speculation about the next #1.** Will likes to be surprised. Never say who "could" or "is poised to" reach #1, and never predict next week's chart. Awards predictions are the one exception, because predicting is their whole point.
- **Plain words, full sentences.** No arrows, no hype words ("smash", "juggernaut", "banger"), and no "it's worth noting". Avoid em-dash asides. Use a comma or a new sentence instead.

## 2. Formatting conventions

| Thing | Write it as | Notes |
|---|---|---|
| Song titles | ‘Single Curly Quotes’ | Commas and periods go inside: ‘Raise Em Up,’ / ‘Girl Crush.’ Short forms are fine on second mention (‘Dime Store’, ‘Word’). |
| Album titles | *Italics* (`<i>…</i>` in articles.json) | Don't put albums in quotes, so they never get confused with songs. |
| Artists | Plain, as the site spells them (data.json) | Link the first mention with `[[Artist]]`. Features read "X and Y's ‘Song’" or "X featuring Y". |
| Chart moves | `8-5`, "jumps 8-5", "slips 6-7", "falls 2-4", "rebounds 6-5", "vaults 20-15" | Use a hyphen with no spaces. Use "holds at #6" for no change. |
| Positions | `#1`, `#2`, `#10` | Always #1, never "No. 1" (Will, 2026-11-06; all old articles converted). "Number One" is spelled out only in headlines. |
| Tiers | Top 5, Top 10, Top 20 | Always capitalized. Write "a new peak", "a new high", "highpoint". |
| Leaders | "six-week leader", "1-week leader", "her #3-peaking ‘Dear Future Husband’" | |
| Awards | **Greatest Gainer** trophy | Capitalized. |
| Charts | **Hot 20** (country), **Pop 10** (pop) | Never write "Top Country Songs" or "Pop Songs" (old names) except when quoting history. |
| Counts | Words for one to nine, numerals for 10+ | "fourth Top 5", "13th #1 single", "27th week on the chart". |
| Dates | "the week of September 24", "in November 2019" | Award shows are "the 2023 show" (show year, not Year-End year). |

## 3. The weekly recap (recaps.json)

**Headline.** Write it in Title Case with a semicolon between the two biggest stories, and name the #1 first:
- "‘Girl Crush’ Still Number One; Urban and Church Enter Top 5"
- "‘Dime Store’ Holds #1; Ronnie Dunn is Greatest Gainer for Third Week"
- "Eric Church Stays at Number One; Cody Jinks is the Greatest Gainer"
- New #1: "‘X’ Rises to Number One" / "X Returns to Number One for the First Time Since 2019".

**Body.** Use one long paragraph for the Hot 20, then one for the Pop 10 that opens "Over on the Pop 10,". Walk the chart from the top down:
1. **#1:** how many weeks, and the career context: #1 count, longest leaders, first #1 since when.
2. **#2 to #5:** "Underneath X is Y…", then new peaks and anything new to the Top 5.
3. **Greatest Gainer:** name it and give the move.
4. **#6 to #10:** group songs that move together ("The next three songs likewise rise one rung").
5. **Songs leaving the Top 10** and anything notable lower down (a long run, a record).
6. **Debuts,** with context such as "his first charting single" or "the first single from…".
7. **Drop-offs,** when they matter.

The Pop 10 paragraph is shorter. It covers the #1, the Top 5, and one "In other news" note.

**Fanfare for milestones** (Will, 2026-10-30). A first #1 in years, a first Top 10, or a record gets a short chart history: how long the drought was, what charted in between, and the real-world singles and albums that didn't chart. When you give a count ("four Top 10s"), name the songs.

## 4. Chart Beat articles (articles.json)

Every article fits one of three **buckets** (the `bucket` field is internal and never shown):
- `analysis`: the critic's voice. Awards predictions, what makes a hit, and trends.
- `history`: the chart historian. Streaks, records, anniversaries, "This Week in…".
- `relevance`: real-world context. Tributes, legacies, and how the chart lines up with radio and the awards.

**Shape.**
- **Headline:** a sentence that makes a claim, in sentence case. Example: "Cassandra Coleman leads the Album of the Year race, and one-hit albums could fill half the field". Questions and "How X…" forms are fine, as on the blog ("How Luke Combs Turned ‘Beautiful Crazy’ Into One of the Biggest Hits in Years").
- **Dek:** one sentence on what the piece covers.
- **First paragraph:** the thesis and why it matters now. In 2-3 sentences, a reader should know the answer.
- **Middle:** 3-6 paragraphs. Each one opens with a bold lead-in (`<b>The locks.</b>`, `<b>What it takes.</b>`) and backs its claim with chart facts.
- **Ending:** one line with the verdict, or the panel (below). Don't summarize. The blog ends on a verdict or a question to readers, never on "In conclusion".

**Expert panel.** These are fictional, so never use real people's names:
- **Mitzi Tallyho** is the chart data editor and goes by the numbers.
- **Sebastian Crescendo** is the senior music critic and goes by craft.
- **Bobbie Jo Rhinestone** hosts the fan podcast *Windows Down* and goes by heart.

Give each one a short quote with a different take.

**Facts first.** Every number comes from data.json, runs.json or awards.json. Before writing "never charted" or "first since", match names loosely, ignoring punctuation and checking features in combined artist names. For example, "Stephen Wilson Jr" has no period and "Kaitlyn Butts" is spelled differently. Never mention chart points anywhere except the About page.

## 5. Awards predictions

Will's blog set the format with "ACM Awards 2019 Winner Predictions!", where every category gets a pick plus a short paragraph of reasoning.
- Every prediction article has a `ballot` box (title, items with `[[Artist]]` links, optional note). It renders right under the first paragraph, so the picks aren't buried.
- **Nomination pieces** list the full predicted field plus one alternate.
- **Winner pieces** use three items: **Will win**, **Should win**, **Dark horse**. The ballot title is "Our picks: <Category>".
- **Song of the Year is about the writing** (Will, 2026-11-06). Build the piece around who wrote the song, what it says, its key lines and how it's built. Research credits, artist quotes and lyrics with web search, quote only lines you've verified, and keep chart stats as background. Chart success and production belong in **Record of the Year** (pop) and **Single of the Year** (country). Country Song of the Year works the same way.
- Explain the reasoning with history ("the Year-End #1 won 12 of 14 Record of the Year shows") and say plainly what Willboard thinks. Always note that Will picks the nominees and winners, and that we haven't seen them.
- Never state country winners before Will adds them on show night. Never look at an unreleased show's rows in the Nominees sheet.

## 6. Single and album reviews (if we run them)

Use the blog's format: "Single Review: Artist – ‘Song’". Cover what the song is about, the production, and the vocal, then end with **Grade: X/10**.

## 7. Before publishing: checklist

- [ ] Song titles are in ‘curly single quotes’ with punctuation inside, and albums are in italics.
- [ ] It uses #1, Top 5, Hot 20 and Pop 10, with no "No. 1" or old chart names.
- [ ] No chart points, no next-#1 guesses, and no real people quoted as the panel.
- [ ] Every count names its songs, and every "first since" is checked against features.
- [ ] Prediction pieces have a ballot box.
- [ ] No Dolly Parton photo on new articles. Her tribute article keeps `pinUntil` and `tribute`.
