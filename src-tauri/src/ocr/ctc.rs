//! Native Rust CTC (Connectionist Temporal Classification) Greedy Decoder
//!
//! Maps neural network sequence output logits/probabilities to UTF-8 character strings
//! across English, Indonesian, Japanese, Chinese, and Korean scripts.

#[derive(Debug, Clone)]
pub struct CtcDecoder {
    characters: Vec<String>,
}

impl CtcDecoder {
    /// Initialize decoder from a raw list of characters (e.g. from model metadata or dict file).
    /// Automatically prepends "blank" at index 0 and appends space " " at the end if not already present.
    pub fn new(character_list: Vec<String>) -> Self {
        let mut chars = Vec::with_capacity(character_list.len() + 2);
        chars.push("blank".to_string());
        let mut has_space = false;
        for c in character_list {
            if c == " " {
                has_space = true;
            }
            chars.push(c);
        }
        if !has_space {
            chars.push(" ".to_string());
        }
        Self { characters: chars }
    }

    /// Initialize directly with pre-formatted character list where index 0 is already blank.
    pub fn from_full_character_list(characters: Vec<String>) -> Self {
        Self { characters }
    }

    /// Total number of character classes in dictionary.
    pub fn len(&self) -> usize {
        self.characters.len()
    }

    pub fn is_empty(&self) -> bool {
        self.characters.is_empty()
    }

    /// Decode sequence of time-step probability distributions.
    /// `slice`: 1D slice representing a flattened [T, num_classes] matrix.
    /// `t_steps`: number of time steps (T).
    /// `num_classes`: number of classes per time step.
    pub fn decode_slice(&self, slice: &[f32], t_steps: usize, num_classes: usize) -> (String, f32) {
        if t_steps == 0 || num_classes == 0 || slice.len() < t_steps * num_classes {
            return (String::new(), 0.0);
        }

        let mut best_indices = Vec::with_capacity(t_steps);
        let mut best_probs = Vec::with_capacity(t_steps);

        for t in 0..t_steps {
            let offset = t * num_classes;
            let step_slice = &slice[offset..offset + num_classes];

            let mut max_idx = 0;
            let mut max_val = f32::NEG_INFINITY;
            for (idx, &val) in step_slice.iter().enumerate() {
                if val > max_val {
                    max_val = val;
                    max_idx = idx;
                }
            }
            best_indices.push(max_idx);
            best_probs.push(max_val);
        }

        self.decode_indices(&best_indices, &best_probs)
    }

    /// Decode argmax indices and associated confidence values.
    /// Collapses consecutive identical tokens, discards blank token (index 0).
    pub fn decode_indices(&self, indices: &[usize], probs: &[f32]) -> (String, f32) {
        if indices.is_empty() {
            return (String::new(), 0.0);
        }

        let mut decoded_text = String::new();
        let mut selected_probs = Vec::new();
        let mut prev_idx: Option<usize> = None;

        for (i, &idx) in indices.iter().enumerate() {
            // CTC collapse rule: discard if identical to immediately preceding time step
            if Some(idx) == prev_idx {
                continue;
            }
            prev_idx = Some(idx);

            // Discard CTC blank token (index 0)
            if idx == 0 {
                continue;
            }

            // Map valid index to character
            if idx < self.characters.len() {
                decoded_text.push_str(&self.characters[idx]);
                let p = if i < probs.len() { probs[i] } else { 1.0 };
                selected_probs.push(p);
            }
        }

        let avg_conf = if selected_probs.is_empty() {
            0.0
        } else {
            let sum: f32 = selected_probs.iter().sum();
            sum / (selected_probs.len() as f32)
        };

        (decoded_text, avg_conf)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ctc_decoder_basic() {
        let chars = vec!["a".to_string(), "b".to_string(), "c".to_string()];
        let decoder = CtcDecoder::new(chars);
        assert_eq!(decoder.len(), 5); // blank, a, b, c, space
        assert_eq!(decoder.characters[0], "blank");
        assert_eq!(decoder.characters[1], "a");
        assert_eq!(decoder.characters[2], "b");
        assert_eq!(decoder.characters[3], "c");
        assert_eq!(decoder.characters[4], " ");
    }

    #[test]
    fn test_ctc_collapse_consecutive_duplicates() {
        let chars = vec!["h".to_string(), "e".to_string(), "l".to_string(), "o".to_string()];
        let decoder = CtcDecoder::new(chars);
        // "h-e-l-l-o" where second 'l' is separated by blank:
        // indices: [1, 1, 0, 2, 2, 0, 3, 3, 0, 3, 3, 0, 4, 4]
        // 1='h', 2='e', 3='l', 4='o'
        let indices = vec![1, 1, 0, 2, 2, 0, 3, 3, 0, 3, 3, 0, 4, 4];
        let probs = vec![0.9; indices.len()];

        let (text, conf) = decoder.decode_indices(&indices, &probs);
        assert_eq!(text, "hello");
        assert!((conf - 0.9).abs() < 1e-4);
    }

    #[test]
    fn test_ctc_consecutive_identical_without_blank_collapses() {
        let chars = vec!["A".to_string(), "B".to_string()];
        let decoder = CtcDecoder::new(chars);
        // [1, 1, 1] without blank should produce single "A"
        let indices = vec![1, 1, 1];
        let probs = vec![0.95, 0.96, 0.94];

        let (text, conf) = decoder.decode_indices(&indices, &probs);
        assert_eq!(text, "A");
        assert!((conf - 0.95).abs() < 1e-4);
    }

    #[test]
    fn test_ctc_decode_slice_matrix() {
        let chars = vec!["X".to_string(), "Y".to_string()];
        let decoder = CtcDecoder::new(chars); // classes: 0: blank, 1: X, 2: Y, 3: space (4 classes)

        // 3 time steps, 4 classes each
        #[rustfmt::skip]
        let matrix = vec![
            0.1, 0.8, 0.05, 0.05, // step 0 -> class 1 (X, prob 0.8)
            0.9, 0.05, 0.03, 0.02, // step 1 -> class 0 (blank, prob 0.9)
            0.05, 0.05, 0.85, 0.05, // step 2 -> class 2 (Y, prob 0.85)
        ];

        let (text, conf) = decoder.decode_slice(&matrix, 3, 4);
        assert_eq!(text, "XY");
        assert!((conf - (0.8 + 0.85) / 2.0).abs() < 1e-4);
    }

    #[test]
    fn test_ctc_empty_or_all_blank() {
        let chars = vec!["A".to_string()];
        let decoder = CtcDecoder::new(chars);
        let indices = vec![0, 0, 0];
        let probs = vec![0.99, 0.99, 0.99];

        let (text, conf) = decoder.decode_indices(&indices, &probs);
        assert_eq!(text, "");
        assert_eq!(conf, 0.0);
    }
}
