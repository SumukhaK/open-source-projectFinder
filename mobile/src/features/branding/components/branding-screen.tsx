import React, { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { BrandMark } from '../../../components/brand-mark';
import { BrandLoader } from '../../../components/brand-loader';
import { AppearanceControls } from '../../../components/appearance-controls';
import { branding } from '../../../config/branding';
import { useTheme } from '../../../lib/theme';

export function BrandingScreen() {
  const { mode } = useTheme();
  const colors = branding.themes[mode];
  const [preview, setPreview] = useState(false);
  return <SafeAreaView style={[styles.root, { backgroundColor: colors.background }]}>
    <ScrollView contentContainerStyle={styles.content}>
      <View style={styles.header}><BrandMark mode={mode} size={38} />
        <Text style={[styles.wordmark, { color: colors.text }]}>RepoRadar</Text></View>
      <View style={styles.hero}>
        <BrandMark mode={mode} size={112} />
        <Text style={[styles.eyebrow, { color: colors.accent }]}>FOLLOW YOUR NEXT IDEA</Text>
        <Text accessibilityRole="header" style={[styles.title, { color: colors.text }]}>Find where your{'\n'}idea already lives.</Text>
        <Text style={[styles.description, { color: colors.muted }]}>Discover open-source projects with a similar purpose. Text and voice discovery are coming next.</Text>
      </View>
      <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <Text accessibilityRole="header" style={[styles.cardTitle, { color: colors.text }]}>Make it yours</Text>
        <Text style={[styles.caption, { color: colors.muted }]}>Appearance</Text>
        <AppearanceControls />
      </View>
      <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <Text accessibilityRole="header" style={[styles.cardTitle, { color: colors.text }]}>A compass for discovery</Text>
        <Text style={[styles.caption, { color: colors.muted }]}>Bracket Navigator will guide every loading moment.</Text>
        <View style={styles.preview}>
          {preview ? <BrandLoader mode={mode} size={72} label="Loading preview" /> : <BrandMark mode={mode} size={72} />}
        </View>
        <Pressable accessibilityRole="button" onPress={() => setPreview(!preview)}
          style={[styles.previewButton, { borderColor: colors.border }]}>
          <Text style={{ color: colors.accent, fontWeight: '600' }}>{preview ? 'Stop animation preview' : 'Preview loading animation'}</Text>
        </Pressable>
      </View>
      <Text style={[styles.footer, { color: colors.muted }]}>Your next project starts with discovery.</Text>
    </ScrollView>
  </SafeAreaView>;
}
const styles = StyleSheet.create({
  root: { flex: 1 }, content: { padding: 24, gap: 20, maxWidth: 560, width: '100%', alignSelf: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12 }, wordmark: { fontSize: 23, fontWeight: '700' },
  hero: { paddingVertical: 28, alignItems: 'center', gap: 18 }, eyebrow: { fontSize: 11, fontWeight: '700', letterSpacing: 2 },
  title: { fontSize: 32, lineHeight: 39, fontWeight: '700', textAlign: 'center' },
  description: { fontSize: 16, lineHeight: 25, textAlign: 'center', maxWidth: 360 },
  card: { borderWidth: 1, borderRadius: 20, padding: 20, gap: 12 }, cardTitle: { fontSize: 18, fontWeight: '600' },
  caption: { fontSize: 14, lineHeight: 22 },
  preview: { minHeight: 130, alignItems: 'center', justifyContent: 'center' },
  previewButton: { minHeight: 48, borderWidth: 1, borderRadius: 12, padding: 12, alignItems: 'center', justifyContent: 'center' },
  footer: { textAlign: 'center', fontSize: 12, paddingVertical: 8 },
});
