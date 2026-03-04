import { useState, useRef, useCallback } from 'react';
import styles from './StoryPage.module.css';

/* ─── TTS hook ──────────────────────────────────────────────────────────── */

function useTTS() {
  const [isPlaying, setIsPlaying] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const audioRef = useRef(null);

  const play = useCallback(async (text) => {
    // If already playing, stop
    if (audioRef.current) {
      audioRef.current.pause();
      URL.revokeObjectURL(audioRef.current._blobUrl);
      audioRef.current = null;
      setIsPlaying(false);
      return;
    }

    setIsLoading(true);
    try {
      const res = await fetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) {
        const err = await res.text();
        console.error('[TTS] Error:', err);
        return;
      }
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio._blobUrl = url;
      audioRef.current = audio;

      const cleanup = () => {
        URL.revokeObjectURL(url);
        audioRef.current = null;
        setIsPlaying(false);
      };
      audio.addEventListener('ended', cleanup);
      audio.addEventListener('error', cleanup);

      setIsPlaying(true);
      await audio.play();
    } catch (err) {
      console.error('[TTS] Fetch failed:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { isPlaying, isLoading, play };
}

/* ─── Play button ───────────────────────────────────────────────────────── */

function PlayButton({ text }) {
  const { isPlaying, isLoading, play } = useTTS();
  return (
    <button
      className={styles.playBtn}
      onClick={() => play(text)}
      disabled={isLoading}
      title={isPlaying ? 'Stop reading' : 'Read aloud'}
      aria-label={isPlaying ? 'Stop reading' : 'Read aloud'}
    >
      {isLoading
        ? <span className={styles.playSpinner} />
        : isPlaying ? '⏹' : '▶'}
    </button>
  );
}

/** Cover page — shown as "page 0" before the story pages */
export function CoverPage({ story }) {
  const charNames = [
    ...(story.pages?.[0]?.characters_present ?? []),
  ].slice(0, 6);

  return (
    <div className={styles.coverPage}>
      {/* Illustration area */}
      <div className={styles.coverImageArea}>
        {story.cover_image_url ? (
          <img src={story.cover_image_url} alt="Book cover" className={styles.coverImage} />
        ) : (
          <div className={styles.coverImagePlaceholder}>📖</div>
        )}
        {/* Title overlay on the image */}
        <div className={styles.coverOverlay}>
          <h2 className={styles.coverTitle}>{story.title}</h2>
          {charNames.length > 0 && (
            <p className={styles.coverCharacters}>Featuring: {charNames.join(', ')}</p>
          )}
        </div>
      </div>

      {/* Moral tagline below the image */}
      <div className={styles.coverMoralArea}>
        <div className={styles.coverMoral}>
          <em>"{story.moral_summary}"</em>
        </div>
        <PlayButton text={story.title} />
      </div>
    </div>
  );
}

/** Final / "The End" page — shown after all story pages */
export function FinalPage({ story }) {
  if (story.the_end_image_url) {
    return (
      <div className={styles.finalPage}>
        <div className={styles.finalImageArea}>
          <img src={story.the_end_image_url} alt="The End" className={styles.finalImage} />
          <div className={styles.finalPlayOverlay}>
            <PlayButton text="The End" />
          </div>
        </div>
      </div>
    );
  }

  // Fallback when image isn't available
  return (
    <div className={styles.finalPage}>
      <div className={styles.finalEmoji}>⭐</div>
      <h3 className={styles.finalTitle}>The End</h3>
      <p className={styles.finalMoral}>{story.moral_summary}</p>
      {story.review_notes && story.review_notes !== 'Story approved with no issues.' && (
        <p className={styles.finalNotes}>{story.review_notes}</p>
      )}
      <div className={styles.finalFallbackPlay}>
        <PlayButton text="The End" />
      </div>
    </div>
  );
}

/** An individual story page with illustration + narrative text */
export default function StoryPage({ page, totalPages }) {
  return (
    <div className={styles.page}>
      {/* Illustration */}
      <div className={styles.imageWrapper}>
        {page.image_url ? (
          <img
            src={page.image_url}
            alt={`Illustration for page ${page.page_number}`}
            className={styles.image}
          />
        ) : (
          <div className={styles.imagePlaceholder}>
            <span>🖼️</span>
            <span>
              {page.scene_description
                ? page.scene_description.slice(0, 120) + '…'
                : 'Illustration coming soon'}
            </span>
          </div>
        )}
        <div className={styles.pageBadge}>
          Page {page.page_number} of {totalPages}
        </div>
      </div>

      {/* Narrative text */}
      <div className={styles.textArea}>
        <div className={styles.textRow}>
          <p className={styles.storyText}>{page.text}</p>
          <PlayButton text={page.text} />
        </div>
        {page.characters_present?.length > 0 && (
          <div className={styles.characterTags}>
            {page.characters_present.map((c, i) => (
              <span key={i} className={styles.tag}>{c}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
