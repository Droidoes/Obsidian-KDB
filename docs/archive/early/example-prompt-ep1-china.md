# Example Prompt — EP1 - The Journey of China.md
_Offline reconstruction via `prompt_builder.build_prompt()`. No API call was made to generate this file._

## Meta

- **Source:** `KDB/raw/EP1 - The Journey of China.md`
- **Source length:** 24,636 chars
- **Context pages selected:** 0 (body-free; slug + title + page_type + outgoing_links only)
- **System prompt length:** 6,051 chars
- **User prompt length:** 30,217 chars
- **Total prompt length:** 36,268 chars

---

## System prompt

````
# KDB Compiler Invariants (KDB-Compiler-System-Prompt.md)

You are the **semantic compiler** for Joseph's Obsidian KDB. You are invoked by `kdb_compiler/compiler.py` with one source file at a time. Your only output is a structured JSON **page-intents** payload conforming to `compile_result.schema.json`. Python owns every filesystem write, path decision, and runtime metadata stamp.

## What you own vs. what Python owns

**You (LLM) own — semantic intent:**
- Which concepts exist in this source
- What each page's title, body, and logical identity (`slug`) should be
- What links exist *within the body text* you emit (`[[Slug]]` references)
- Which sources support which pages (`supports_page_existence`)
- Your confidence in each page
- Contradictions worth logging

**Python owns — mechanics:**
- Filesystem paths (you emit `slug`, Python resolves to `KDB/wiki/concepts/<slug>.md`)
- Frontmatter generation (`raw_path`, `raw_hash`, `raw_mtime`, `compiled_at`, `compiler_version`, `schema_version_used`)
- Timestamps, run IDs, versions
- `incoming_links_known` (Python reconciles from `outgoing_links` across all pages)
- `index.md` and `log.md` (Python regenerates/appends deterministically from manifest + runs)

Do not emit paths. Do not emit timestamps. Do not emit frontmatter. Do not emit `incoming_links_known`.

## Ground Rules

1. **Ground everything in the source file.** Never invent facts, citations, URLs, dates, or author names. If the source doesn't support a claim, omit it.
2. **Prefer many small concept pages over monolithic articles.** One page per distinct concept.
3. **Link aggressively within your emitted page bodies.** Use `[[slug]]` syntax (Python resolves to the actual wikilink during apply). But: never link to a slug that has no basis in the current source or in the manifest snapshot passed to you.
4. **Do not edit `raw/`.** Read-only input.
5. **Do not touch Human Side folders** (anything outside `KDB/`). Off-limits.
6. **Obsidian-flavored Markdown only.** `[[slug]]`, `[[slug|display]]`, `[[slug#heading]]`. No HTML.
7. **Contradictions between sources** — do not pick a winner. Emit a `log_entry` flagging the conflict; Python appends it to `wiki/log.md`.
8. **Schema compliance is mandatory.** Malformed output aborts the run before any vault write.

## Page Types You May Emit

- `summary` — one per raw source. Logical `slug` derives from the source file's stem. Contains a short abstract + links to concepts/articles derived from this source.
- `concept` — atomic idea (e.g., "attention-mechanism"). May be supported by multiple sources over time.
- `article` — longer synthesis across multiple concepts. Emit only when source content warrants narrative synthesis.

You do **not** emit `index` or `log` pages. Those are Python-owned.

## Page Update Semantics

You emit **full page bodies** (not patch operations). If a page already exists in the manifest snapshot, you emit the new full body — Python overwrites the file. To merge new material with existing content, you must read the existing body from the manifest snapshot and produce a merged version.

Do not emit partial updates, diffs, or surgical edits. One page = one body.

## Linking Discipline

- Forward links: write `[[slug]]` inside your page body text wherever supported by the source.
- Backlinks: you do **not** manage these. Python reconciles `incoming_links_known` from everyone's `outgoing_links` in the manifest. You may include a prose "See also" section only when the current source *explicitly* cites or discusses the linked concept — never as a routine add.
- Link removal: only remove a link from your emitted body if (a) the source never mentioned the target, or (b) the target is factually wrong given the source.

## What You Must Output (per compile call)

A single JSON object conforming to `compile_result.schema.json`. The top-level `compiled_sources[]` entry for this source contains:

- `source_id` — canonical path of the source you were given (echo back)
- `summary_slug` — slug for the summary page (stem of the source file, kebab-cased)
- `concept_slugs[]` — slugs of all concept pages you created or updated
- `article_slugs[]` — slugs of all article pages you created or updated (often empty)
- `pages[]` — one entry per page you're emitting:
  - `slug`, `page_type`, `title`, `status` (`active` | `stale` | `archived`)
  - `supports_page_existence[]` — source_ids that justify this page existing
  - `outgoing_links[]` — slugs this page links to
  - `confidence` (`low` | `medium` | `high`)
  - `body` — full markdown body (no frontmatter; Python prepends it)
- `log_entries[]` — one entry per notable event (contradictions, ambiguity, low-confidence decisions); Python appends to `wiki/log.md`

## Self-check before emitting

- [ ] No path strings (no `KDB/...`, no `.md` suffixes in identifiers)
- [ ] No frontmatter in `body` fields (Python prepends it)
- [ ] No timestamp / version / run-id fields
- [ ] No `incoming_links_known` field
- [ ] Every `outgoing_links[]` target exists in `pages[]` this compile OR in the manifest snapshot you were given
- [ ] Every `supports_page_existence[]` source_id is real (the current source, or one in the manifest)
- [ ] No invented citations, URLs, author names, or dates
- [ ] Every `body` is valid Obsidian markdown


---
RESPONSE CONTRACT (non-negotiable):
- Return EXACTLY ONE JSON object. No other output.
- No markdown code fences around the object.
- No prose before or after the object.
- The object MUST satisfy the schema provided in the user message exactly.
- The "source_id" field MUST echo the provided source_id verbatim.
- Every page's "supports_page_existence" array MUST contain the provided source_id.
- Use the "warnings" array for non-fatal observations about the source
  (ambiguous terms, unresolved references, uncertain categorization). DO NOT
  fabricate pages to satisfy the schema. If the source genuinely contains
  nothing knowledge-worthy, emit a single summary page whose body explains
  that — with honest content — and leave concept/article lists empty.
````

---

## User prompt

````
source_id: KDB/raw/EP1 - The Journey of China.md

## SOURCE CONTENT

Video Link: [General History of China EP1 | 中国道路 【China Movie Channel ENGLISH】 | ENG DUB](https://www.youtube.com/watch?v=sH140nwxF_g&list=PLSyuJLM8uqBYm_VaFMZPkk9E3UUxtaR0E)
Published Date: Apr 27, 2022
Channel: [China Movie Channel ENGLISH](https://www.youtube.com/@1905-English)

# Introduction to China's History and Spirit

This is a magical land. The all-inspiring landscape cradled to life in all its glory gave rise to a great country: China.

This vast land is home to a civilization thousands of years old and rich in history and culture. It is home to a great nation: the Chinese.

In this vast and magical land, countless historical events have unfolded with twists, turns, and hardships for its people.

Resilience, virtues, adventurousness, family loyalty, and peacemaking—all of these run deep in the blood of the Chinese.

Despite every trial that may come their way, the Chinese people always rise to the challenge, sailing through the storm to victory.

Overcoming every obstacle and uncertainty, the Chinese people pursue the right path with stamina and calm, achieving success for China and for the rest of the world.

This is the history of China: rich and varied, sophisticated and splendid, ancient and endless. China's history, with its countless legendary events, is rooted in and has blossomed in this land.

In this modern era, China's millennia of history are a precious heritage.

History is like a lighthouse, lighting the road to China's restoration. It is like a loving mother by the cradle of China's dreams.

# The Axial Age and Hundred Schools of Thought

In the period between 800 and 200 BC, men of great stature rose to prominence in both East and West: Laozi, Confucius, Sakyamuni, Aristotle, Mencius.

These great thinkers took the world stage either around the same time or one after another.

==In the West, this period has been called the Axial Age. In China, it's called the Age of a Hundred Schools.==

In both East and West, the period is remembered as an age of discovery and awakening.

# Mozi and His Philosophy

The Mozi Memorial Museum in the city of Tengzhou. In contrast to other great Chinese thinkers, Mozi cut a solitary figure. His statue portrays him journeying in sackcloth with a bag over his shoulder.

Mozi lived in an age of incredible inventions, inventions that he skillfully assimilated when putting his philosophy into practice.

In an age of civil war, Mozi and his disciples lived like ascetic monks, believing strongly in an ethic of self-sacrifice, opposing war, and supporting universal love.

Mozi's universal love transcended bounds of class and hierarchy, and he opposed all.

# Laozi and Other Schools

In contrast, Laozi's Taoist philosophy advocated non-interventionism, the eradication of desire, and harmony with nature.

These were only two of the countless thinkers and philosophies to emerge in that period. There was the school of Yin and Yang, which explained all changes in terms of diametrically opposed forces; of Legalism, advocating governance through law; of political strategists, focusing on political negotiation. All took different approaches as to how to live with nature and with one another.

But all were inextricably tied to one particular school of thought: Confucianism. It was founded by Confucius, acclaimed in China as the greatest teacher of all time.

# Confucianism and Its Teachings

With benevolence, ceremonial rights, and virtue as the thrust of his teaching, Confucius' goal was peace on a personal, national, and world level.

The teachings of Confucius would become the most important traditional body of thought in China in the last two thousand years. Yet during his lifetime, no warlord ever favored his philosophy. He was forced to wander from state to state.

About a century after Confucius' death, another sage, Mencius, picked up the work and continued preaching the Confucian philosophy. But no warlord accepted Mencius' teachings either.

Still, no state had accepted Confucianism as a governing philosophy, and factions began to emerge. ==In the eyes of many, Li Si, favorite disciple of the Confucian philosopher Xunzi, even became the arch enemy of Confucianism because of his leading role in a Qin dynasty campaign to eliminate books and intellectuals.==

==Confucian philosophy was almost wiped out.==

# Revival of Confucianism in the Han Dynasty

The Museum of Confucian Artifacts in the city of Qufu holds 36 silk paintings of the series "Confucius the Sage" from the second half of the 15th century.

Most of the paintings depict Confucius as a destitute wanderer, but among them is a surprise: homage to Confucius by the Emperor Gaozu of the Han dynasty.

==The founding emperor of the Han dynasty, Liu Bang, made this most elaborate offering just 18 years after the elimination of books. It was the first recorded instance of a head of state performing the ritual of public homage for Confucius, even if Liu Bang's real motive was to use the Confucian notion of rights to bolster his position as emperor.==

Founded amid turmoil in 220 BC, the Han dynasty desperately needed peace. Taoist non-interventionism might have been a better fit for its governing needs.

==The true revival of Confucianism came six decades later, during the reign of another Han emperor. On the surface, his was a golden age, but underneath lay a complex web of conflicts. To turn things around, the dynasty needed a new political philosophy.==

==Enter the great Confucian scholar Dong Zhongshu. It was he who put forward the famous proposal exalting Confucianism over all other schools of thought.==

This did not mean banishing all non-Confucian philosophical thought. Confucianism reformed itself by incorporating the best principles of Yin-Yang, Legalism, Mozi, and so on.

To its original principles of benevolence, righteousness, ceremonial rights, and music, it added support for centralized authority and the importance of political and social hierarchy.

==Overnight, Confucian thought became a classic and a bona fide.==

# Confucianism in Later Dynasties

The Han dynasty came to an end in 220 AD. Around that time, Buddhism was introduced into China. By the height of the Tang dynasty, Confucianism, Buddhism, and Taoism were all well accepted. But following the demise of the Tang dynasty in the early 10th century, Confucianism once again lost its luster during centuries of warfare.

When much of China was reunified under the Song dynasty, a large number of Confucian scholars emerged. Among them were advocates of Neo-Confucianism, including Zhang Zai, Cheng Hao, Cheng Yi, and Zhu Xi.

This Cheng-Zhu school followed the philosophy of ruling by rights to further promote Confucian rules of inheritance, chastity, and filial piety.

Neo-Confucianism became the most stabilizing and dominant official philosophy of the Song. So began the second revival of Confucianism.

Over time, however, the Cheng-Zhu school of thought grew rigid, and its philosophy, once vibrant, became fossilized. By the opening years of the Ming dynasty in the 14th century, Confucianism desperately needed someone to showcase its underlying vibrancy and vitality.

Most young candidates for public office clung to the conservative thought of Zhu Xi, but an enterprising 16-year-old had traveled through northern China and vowed to travel even more to see the world. He was Wang Yangming.

His laid-back personality contributed in part to his tumultuous and legendary life. It also fostered a new Confucian sage.

His wealth of life experience and sharp mind led Wang Yangming to a new understanding of Confucianism, Buddhism, and Taoism. He proposed the notions of principles residing within and putting knowledge into action. His ideology, known as Learning of the Heart-Mind, proved.

# Evolution of Chinese Thought

Traditional Chinese thinking is based primarily on the thoughts of Confucius. Confucianism evolved through interacting with other philosophies: Legalism, Buddhism, Taoism.

For two millennia, these schools of thought have influenced behavior, manners, morality, and political thinking. They have contributed to both the success of rulers and their demise.

# Legalism and the Qin Dynasty

In 361 BC, Shang Yang, a philosopher well versed in the law, proposed a reform to Duke Xiao of the Qin state. The reform was driven by the doctrine of Legalism, and it was aimed at strengthening the power of the state.

Shang Yang enacted a series of strict laws that saw the rapid rise of the Qin state.

A hundred years after Shang Yang's reform, Qin Shi Huang annexed six rival states, founding the mighty Qin dynasty and unifying China for the first time.

But the same harsh laws also led to the dynasty's demise after just 15 years—clear evidence of one simple truth: that harsh laws alone are not enough for a peaceful and long-lasting reign.

# Ruling by Rights and Law

Dynasties ruled for almost a thousand years. In that time, two political philosophies were proposed and implemented: ruling by rights and ruling by law.

How could these contrasting approaches be integrated? It was a problem that neither Qin Shi Huang nor the highly capable Han Emperor Wu was able to solve.

In Emperor Wu's old age, his policy of exceedingly lavish state undertakings became a great burden for the people. The Han dynasty was following the Qin dynasty to the brink of destruction.

Reflecting on the errors of his ways, in 89 BC, Emperor Wu issued the Luntai Edict, aimed at letting the people enjoy adequate rest in order to allow them to live a life of prosperity.

This edict of pain and regret not only saved the Han dynasty; it also broadened the scope of thinking on the proper government of the state. For over 2,000 years, dynastic rulers have been progressing through trial and error. Now, China's traditional political system gradually matured, becoming ever more highly developed.

To motivate citizens to clear land and focus on farming, the system of equal distribution of farmland was introduced under the Northern Wei dynasty. The three departments and six ministries structure of public administration was established under the ensuing Sui dynasty, which also introduced imperial public examinations for entry into the civil service.

The comprehensiveness of its institutions, the emergence of talents, and rises in productivity all contributed to a prosperous, highly cultured state. It has been called the second peak of civilization in feudal China. Still, even the mighty Tang dynasty was unable to last.

# Political Systems and Corruption

At the Shaolin Temple, a shrine to martial arts, there was one secret routine called 36 Techniques by Emperor Tai. It is said to have been devised by Zhao Kuangyin, the first Song emperor.

Zhao, born in 927 AD, was a professional soldier for only 12 years before instigating the Chenqiao Mutiny and seizing the throne.

He had grown up amid civil war in the era of Five Dynasties and Ten Kingdoms. The endemic infighting had to be resolved if China were ever to be reunified.

The steps he took rose to the greatness expected of the founding emperor of a prosperous dynasty.

As Emperor Taizu, he implemented a series of political, military, and economic measures that proved very effective in preventing mutinies and coups d'état. These measures finally made his reign a lasting one in a unified China.

To tame his generals, Emperor Taizu appointed intellectuals to key positions alongside them. The entire state began to stabilize under this form of administration.

==But in reality, every political system in Chinese history has been affected by the same plague: corruption. As long as corruption is left untreated, any foundation, however solid, will inevitably rot.==

The Ming city wall in Nanjing, having withstood the elements for over 600 years, it remains as solid today as the day it was built. Up close, you'll find inscriptions on every brick in the wall.

Under this meticulous system, every one of the wall's hundreds of millions of bricks could be traced back to its origin.

Zhu Yuanzhang, founder of the Ming dynasty, had first-hand experience of corrupt officials under the previous dynasty. He spared no brutal punishment in dealing with the problem.

==In 1382, over 1,300 officials implicated in the forgery of official documents were all dealt with swiftly.==

==Three years later, a case involving the treasury's handling of grain led to the execution of some 30,000 officials, great and small.==

Zhu Yuanzhang devoted his life to building his ideal world. Yet corruption was an integral part of the feudal system. He was unable to eliminate it completely, nor was it possible for him to do so.

When the last emperor of the Ming dynasty, Chongzhen, was about to commit suicide, his bureaucrats had all gone. He died a lonely man and wrote his final edict in blood to vent his hatred of corrupt officials.

During the seventeen years of my reign, the heavens shed their anger on me on several occasions. I was three times captured by the enemy. The rebels have advanced nearly all the way to the capital. I was led astray by my advisors. Kill the bureaucrats if you wish, but do not vandalize the mausoleum. Do not harm the people.

Corruption has brought down many dynasties. The last Zhou emperor preferred dalliance to duty. As his enemies closed in, he was singing courtyard flowers to his concubine.

When King You set beacons ablaze to assemble his warlords just to amuse his concubine, the Zhou dynasty was doomed to fail.

When King Zhou of the Shang dynasty thought the heavens permitted him to kill as he pleased, the Shang dynasty was doomed to fail.

==Corrupt politicians exacerbated social problems. When things deteriorated past the point of reconciliation, the last resort was often to arms.==

# Overthrow of Dynasties and Warfare

King Wu of Zhou realized this some 3,000 years ago. In 1046 BC, he massed his troops to overthrow the Shang dynasty.

For enterprises like this, divination was used to probe the will of the heavens. The omens were not auspicious. King Wu gave the order to march all the same. The inauspicious omens began to make themselves felt.

When King Wu's army reached the battlefield, a violent storm broke upon them. Heaven appeared to be venting its anger on them.

King Wu's battle cries echoed to the skies and across the battlefield. Once again, he defied the apparent will of the heavens. So began a bloodbath in the wilderness.

But Wu came out victorious. The Shang dynasty was overthrown.

Wars put China's strategists to the test. They also demonstrated the determination of the Chinese to better themselves. King Wu had no time for fatalism.

He led the Chinese out of the trap of superstition, and in the ceremonial rights of his dynasty, the Zhou, the key emphasis was on ethics and morality.

# Warfare and National Character

Warfare over thousands of years has shaped the Chinese view of fate and of the world. It forged and shaped the national character.

Some two thousand years ago, what began as a military gambit turned into a crucial struggle. It began when Emperor Wu of the Han dynasty lured a Hun chieftain and his army to a place called Mayi.

The Huns had been raiding the northwest for 70 years. Emperor Wu had had enough. He had 300,000 troops lying in wait to destroy the Huns.

But the Huns realized it was a trap and withdrew. The Mayi gambit failed.

Emperor Wu then faced a dilemma: should he compromise and negotiate a peace treaty, or should the nation unite to fight the Huns in an all-out war?

Eventually, Emperor Wu chose to fight.

In 133 BC, he launched a war that would last 52 years.

Three great battles stand out: Henan, Hexi, and Mobei.

Chinese heroes, including Li Guang, Wei Qing, and Huo Qubing, made their names in these battles. Li Guang leads by example. Wei Qing is innovative in strategy. As long as Li Guang guards our borders, no Hun will dare to violate them.

These lines recall the heroism and camaraderie of the times. A sense of resolve ran deep in the blood of the Chinese.

The war was as much an ordeal for the nation as for the warriors in the field. Once it began, military expenditures soared. The years of fighting took their toll on the accumulated wealth of the Han dynasty.

But Emperor Wu did not give in. By implementing a series of economic reforms, the Han dynasty restored its treasury.

In the days of the Western Han dynasty, a river flowed eastward here: the Shule. It carried troops, food, weapons, and horses from the interior to the battlefront.

Battle cries, horns, trumpets, and the neighing of horses rang out day and night.

The front line of the Western Han troops battling the Huns in the deserts of the northwest became the longest front ever seen in northern China. ==In the end, the Huns surrendered, and Western Han took control of the northwest borders.==

# Silk Road and Exploration

The Chinese are not a belligerent people, nor are they inward-looking. China's self-imposed isolation was an accident of history.

The Chinese have always had a pioneering spirit and a strong desire to communicate with the outside world.

It was the Chinese who first established the Silk Road.

For thousands of years prior to the reign of Emperor Wu, no one had ever traveled over land from East to West.

In 138 BC, Zhang Qian set out on a trailblazing journey. During his 23 years of expeditions, he went twice to China's far west.

He established direct and indirect links between the central plains of China and South and West Asia, Europe, and Africa.

The Silk Road became the key route connecting East and West. Ever since, it has been a precious heritage of communication between civilizations.

# Maritime Exploration

The Chinese have also never ceased from maritime exploration. The ocean route known as the Maritime Silk Road was already established under the Han and Tang dynasties.

The sea trade of the Yuan dynasty, a maritime golden age, laid the foundation for early Ming communication with the outside world and for the legendary voyages of Admiral Zheng He.

A recreation of Zheng He's fleet on its maiden voyage: hundreds of ships and thousands of sails dot the ocean—a panorama of a fleet that would voyage under full sail day and night.

Altogether, Zheng He embarked on seven long-distance voyages.

But while his fleet was powerful, it was not aggressive. Rather, Zheng He spread the message of peace and goodwill and shared Chinese knowledge and technology with the people of his ports of call.

Both the overland and the maritime Silk Roads reflected the pioneering, open-minded spirit of the Chinese.

# Open Cities and Cultural Blend

So did China's many open cities. Chang'an under the Tang dynasty at its peak, Bianliang under the Northern Song dynasty, and the Yuan dynasty's Khanbaliq were among the most developed world metropolises of their time. Tang-era Chang'an, with a million people, was the world's most populous city.

There were foreign merchants in the marketplace, polo players in the plaza, and Sogdian girls from Central Asia performing dances far more passionate than the traditional Chinese ones.

It was precisely the blend of people of different colors, clothing, and languages that gave Chang'an its appeal. The mixture also demonstrated the all-embracing attitudes of the Chinese people.

# Ethnic Integration

During the fusion process of the Chinese nation, some ethnic groups came from afar, willing to leave behind their customs in order to assimilate into the land of China.

Others integrated through political marriages or voluntary submission. Yet others were assimilated through warfare or other intense confrontations.

In September 493 AD, Emperor Xiaowen of the Northern Wei dynasty, who was an ethnic Xianbei, led his army of 300,000 and all his officials on an arduous march southward. He succeeded in moving the capital to Luoyang on the central plains. This opened the way for a series of sinification reforms.

Xiaowen took the lead by marrying into the local Han people. He made Han Chinese the official language. He changed Xianbei surnames into Chinese surnames, and he restored shrines to Confucius. He even issued an edict changing the record of the Xianbei people's ancestral origin to Luoyang county.

Such drastic changes provoked internal conflicts that saw the rapid demise of the Northern Wei dynasty.

However, as the Xianbei leader, Emperor Xiaowen accomplished what he saw as his sacred mission. The Xianbei fully integrated into the Chinese family. They have lived in the land of China for generations.

# Political Marriages and Cultural Exchange

In 641, a group was about to set off on a journey. The central figure was a 16-year-old girl wearing a wedding gown and heavily made up. She was to be married to the king of Tibet, Songtsen Gampo. She was Princess Wencheng of the Tang dynasty.

She took with her a very special dowry, including fabrics, sewing and farming equipment, seeds for planting, and most importantly, a large quantity of books—in short, a selection of the fruits of the most advanced civilization of the day.

A team 600 strong accompanying the bride was also very special. It included tradesmen such as blacksmiths, carpenters, and agriculturalists.

Princess Wencheng's marriage had a profound impact on Tibet's economic and social development. This provided a solid foundation for the incorporation of Tibet into China some 500 years later.

# Exile and Longing for Home

China is a magical land. Every ethnic group that lives on this land is strongly attached to it. Together, they make up the great Chinese people.

In the year 1124, an army of 10,000 men was about to be driven out of China. After the Jurchen people overthrew the Liao empire in northern China, the Khitan aristocrat Yelü Dashi was forced to flee far to the west.

It was a difficult journey, with unknown dangers lying ahead. Awaiting them were endless snow-capped mountains and vast deserts with blinding sandstorms.

They kept going further and further until they arrived at the location of present-day Balasagun in Kyrgyzstan, where they founded the Western Liao dynasty.

Such a remote spot was hardly their ideal permanent home.

Dashi built up an impressive empire, but he never returned to China.

==Today, the ethnic Khitan people in Kyrgyzstan number around 500,000. Nearly a thousand years have gone by since their ancestors left China, and still they follow their forefathers' way of life. They still look east to their spiritual home.==

Throughout the millennia, whether journeying to the west or sailing to the south, and wherever in the world they were, the Chinese have had a deep longing for this land.

Even if they live abroad, China is constantly in their minds.

# Cohesive Force and Unification

China is a land that exerts a strong cohesive force—a force that leads to the common Chinese desire for national and territorial unification.

National unification is an awareness that runs deep in the blood of every ethnic group in China. The peoples of China are inseparable. Together, they made the history of the great Chinese nation.

The Chinese civilization is the only one that has continued uninterrupted from ancient times to today. Whether it be classics, history, literature, religion, art, law, or architecture, the different cultures learn from and interact with each other. They develop together.

Culture is the soul of a nation. Heroes are the spiritual backbone of a nation. Countless legends have been born on this land; so have countless heroes.

All of them devoted themselves to this land. Time and again, they sang songs commemorating it, imbuing the land with their charisma and heroism.

# Conclusion: Lessons from History

This is the centuries-long history of China. History comes to us from the ancient past. It brings with it profound thoughts: integrity, peace and tolerance, and an enterprising spirit to press forward.

History brings cultural identity. It brings about changes and transformations. History comes to us sternly or steadily, in heavy and lively strides.

History is the collective past of the Chinese: their experience. It is an infinite repository of lessons on which they can draw.

It is because of their rich trove of history that the Chinese can readily face the challenges that lie ahead. It is because they have experienced hardship that they now cherish each day.

The vast wisdom to be had from history is the foundation of their confidence.

As the Chinese enter a bright future, they aspire to be as open as the ocean to the rivers that flow into it.

## EXISTING CONTEXT (manifest snapshot)
{
  "source_id": "KDB/raw/EP1 - The Journey of China.md",
  "pages": []
}

## RESPONSE SCHEMA
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://obsidian-kdb.local/schemas/compiled_source_response.schema.json",
  "title": "KDB Compiled Source Response (per-call model output)",
  "description": "Exactly one source -> exactly one response object. The LLM emits this shape per compile call. Run-level fields (run_id, success, aggregate errors) are Python-owned and NOT present here; see compile_result.schema.json. This contract is stricter than compile_result.schema.json's pageIntent (all 8 page fields required) so the model must commit to status, support, links, and confidence on every page rather than relying on Python backfill.",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "source_id",
    "summary_slug",
    "pages",
    "log_entries",
    "warnings"
  ],
  "properties": {
    "source_id": {
      "$ref": "#/$defs/sourceId"
    },
    "summary_slug": {
      "$ref": "#/$defs/slug"
    },
    "concept_slugs": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/slug"
      }
    },
    "article_slugs": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/slug"
      }
    },
    "pages": {
      "type": "array",
      "minItems": 1,
      "items": {
        "$ref": "#/$defs/pageIntent"
      }
    },
    "log_entries": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/logEntry"
      }
    },
    "warnings": {
      "type": "array",
      "items": {
        "type": "string"
      }
    }
  },
  "$defs": {
    "slug": {
      "type": "string",
      "description": "Lowercase ASCII kebab-case identifier. No paths, no .md suffixes, no directory separators.",
      "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$",
      "minLength": 1,
      "maxLength": 120
    },
    "sourceId": {
      "type": "string",
      "description": "Canonical relative path of a raw source. The LLM echoes the id it was given verbatim.",
      "pattern": "^KDB/raw/.+",
      "minLength": 1
    },
    "pageType": {
      "type": "string",
      "enum": [
        "summary",
        "concept",
        "article"
      ]
    },
    "pageStatus": {
      "type": "string",
      "enum": [
        "active",
        "stale",
        "archived"
      ]
    },
    "confidence": {
      "type": "string",
      "enum": [
        "low",
        "medium",
        "high"
      ]
    },
    "pageIntent": {
      "type": "object",
      "description": "One page the LLM wants to create or replace (full-body model, D18). Stricter than compile_result.schema.json: all 8 fields required, no Python backfill.",
      "additionalProperties": false,
      "required": [
        "slug",
        "page_type",
        "title",
        "body",
        "status",
        "supports_page_existence",
        "outgoing_links",
        "confidence"
      ],
      "properties": {
        "slug": {
          "$ref": "#/$defs/slug"
        },
        "page_type": {
          "$ref": "#/$defs/pageType"
        },
        "title": {
          "type": "string",
          "minLength": 1,
          "maxLength": 200
        },
        "body": {
          "type": "string",
          "minLength": 1,
          "description": "Full markdown body, no frontmatter. Python prepends frontmatter during apply."
        },
        "status": {
          "$ref": "#/$defs/pageStatus"
        },
        "supports_page_existence": {
          "type": "array",
          "minItems": 1,
          "description": "source_ids that justify this page existing. Every page MUST include the compile call's source_id.",
          "items": {
            "$ref": "#/$defs/sourceId"
          }
        },
        "outgoing_links": {
          "type": "array",
          "description": "Slugs this page's body links to. Must appear in body as [[slug]]. Python reconciles incoming_links_known from these.",
          "items": {
            "$ref": "#/$defs/slug"
          }
        },
        "confidence": {
          "$ref": "#/$defs/confidence"
        }
      }
    },
    "logEntry": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "level",
        "message",
        "related_slugs",
        "related_source_ids"
      ],
      "properties": {
        "level": {
          "type": "string",
          "enum": [
            "info",
            "notice",
            "contradiction",
            "warning"
          ]
        },
        "message": {
          "type": "string",
          "minLength": 1
        },
        "related_slugs": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/slug"
          }
        },
        "related_source_ids": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/sourceId"
          }
        }
      }
    }
  }
}

## EXAMPLE RESPONSE
{
  "source_id": "KDB/raw/EP1 - The Journey of China.md",
  "summary_slug": "example-summary",
  "concept_slugs": [],
  "article_slugs": [],
  "pages": [
    {
      "slug": "example-summary",
      "page_type": "summary",
      "title": "Example Summary",
      "body": "A short summary of what this source is about.",
      "status": "active",
      "supports_page_existence": [
        "KDB/raw/EP1 - The Journey of China.md"
      ],
      "outgoing_links": [],
      "confidence": "medium"
    }
  ],
  "log_entries": [],
  "warnings": []
}
````
