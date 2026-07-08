'use client'

import React, { useState } from 'react'
import toast from 'react-hot-toast'
import Button from '@/components/ui/Button'
import Select from '@/components/ui/Select'
import { generationApi } from '@/lib/api'
import type { BriefGenerationSettings } from '@/components/brief/BriefGenerationPanel'
import type { GenerationCatalog, ModelSuggestion } from '@/types'
import type { SelectOption, SelectOptionGroup } from '@/components/ui/Select'

interface ModelSelectData {
  options: SelectOption[]
  groups: SelectOptionGroup[] | undefined
}

interface ModelSelectorBlockProps {
  catalog: GenerationCatalog | undefined
  wantsVideo: boolean
  genSettings: BriefGenerationSettings
  setGenSettings: React.Dispatch<React.SetStateAction<BriefGenerationSettings>>
  imageModelSelect: ModelSelectData
  videoModelSelect: ModelSelectData
  getSuggestionInputs: () => {
    campaign_name: string
    objective: string
    formats: string[]
    target_audience: string
    offer: string
    product_name: string
    ad_copy_tone: string
    cta: string
    duration_seconds: number
    brand_name: string
  }
}

function ReasonBadge({ reason, applied }: { reason: string; applied: boolean }) {
  return (
    <p className={`text-[11px] mt-1 ${applied ? 'text-emerald-700' : 'text-mid'}`}>
      {applied && '✦ '}{reason}
    </p>
  )
}

export default function ModelSelectorBlock({
  catalog,
  wantsVideo,
  genSettings,
  setGenSettings,
  imageModelSelect,
  videoModelSelect,
  getSuggestionInputs,
}: ModelSelectorBlockProps) {
  const [suggesting, setSuggesting] = useState(false)
  const [suggestion, setSuggestion] = useState<ModelSuggestion | null>(null)
  const [applied, setApplied] = useState(false)

  const copyOptions =
    catalog?.copy_models.map((m) => ({ value: m.id, label: m.label })) ?? [
      { value: 'claude', label: 'Claude copy' },
      { value: 'openai', label: 'GPT copy' },
    ]

  const handleSuggest = async () => {
    const inputs = getSuggestionInputs()
    const hasEnough =
      inputs.campaign_name || inputs.offer || inputs.product_name || inputs.target_audience
    if (!hasEnough) {
      toast.error('Fill in Campaign Name, Offer, or Target Audience first so the agent has context.')
      return
    }
    setSuggesting(true)
    setSuggestion(null)
    setApplied(false)
    try {
      const result = await generationApi.suggestModels(inputs)
      setSuggestion(result)
      // Auto-apply
      setGenSettings((prev) => ({
        ...prev,
        copyModel: result.copy_model || prev.copyModel,
        imageModel: result.image_model || prev.imageModel,
        videoModel: result.video_model && wantsVideo ? result.video_model : prev.videoModel,
      }))
      setApplied(true)
      toast.success('Models analysed and pre-selected — change them freely below.')
    } catch {
      toast.error('Model suggestion failed — pick models manually below.')
    } finally {
      setSuggesting(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* Analyse button row */}
      <div className="flex flex-wrap items-center justify-end gap-3">
        <Button
          type="button"
          size="sm"
          variant="outline"
          isLoading={suggesting}
          onClick={() => void handleSuggest()}
          className="border-accent/40 text-accent hover:bg-accent/[0.06]"
        >
          {suggesting ? 'Analysing…' : '✦ Analyse & suggest models'}
        </Button>
      </div>

      {/* Suggestion reasoning banner */}
      {suggestion && applied && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 px-4 py-3 grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <p className="text-[10px] font-bold text-emerald-700 uppercase tracking-wide mb-0.5">Copy model</p>
            <p className="text-xs font-semibold text-navy">{suggestion.copy_model}</p>
            <p className="text-[11px] text-mid mt-0.5">{suggestion.copy_reason}</p>
          </div>
          <div>
            <p className="text-[10px] font-bold text-emerald-700 uppercase tracking-wide mb-0.5">Image model</p>
            <p className="text-xs font-semibold text-navy">{suggestion.image_model}</p>
            <p className="text-[11px] text-mid mt-0.5">{suggestion.image_reason}</p>
          </div>
          {wantsVideo && suggestion.video_model && (
            <div>
              <p className="text-[10px] font-bold text-emerald-700 uppercase tracking-wide mb-0.5">Video model</p>
              <p className="text-xs font-semibold text-navy">{suggestion.video_model}</p>
              <p className="text-[11px] text-mid mt-0.5">{suggestion.video_reason}</p>
            </div>
          )}
        </div>
      )}

      {/* Dropdowns */}
      <div
        className={`grid grid-cols-1 gap-3 ${
          wantsVideo ? 'md:grid-cols-3' : 'md:grid-cols-2'
        }`}
      >
        <div>
          <Select
            label="Copy model"
            options={copyOptions}
            value={genSettings.copyModel}
            onChange={(e) => {
              setGenSettings((prev) => ({ ...prev, copyModel: e.target.value }))
              if (suggestion) setApplied(false)
            }}
          />
          {suggestion && (
            <ReasonBadge
              reason={suggestion.copy_reason}
              applied={applied && genSettings.copyModel === suggestion.copy_model}
            />
          )}
        </div>
        <div>
          <Select
            label="Image model"
            hint="Groups: Runway, Higgsfield"
            options={imageModelSelect.options}
            groups={imageModelSelect.groups}
            value={genSettings.imageModel}
            onChange={(e) => {
              setGenSettings((prev) => ({ ...prev, imageModel: e.target.value }))
              if (suggestion) setApplied(false)
            }}
          />
          {suggestion && (
            <ReasonBadge
              reason={suggestion.image_reason}
              applied={applied && genSettings.imageModel === suggestion.image_model}
            />
          )}
        </div>
        {wantsVideo && (
          <div>
            <Select
              label="Video provider"
              hint="Groups: HeyGen, Runway, Higgsfield"
              options={videoModelSelect.options}
              groups={videoModelSelect.groups}
              value={genSettings.videoModel}
              onChange={(e) => {
                setGenSettings((prev) => ({ ...prev, videoModel: e.target.value }))
                if (suggestion) setApplied(false)
              }}
            />
            {suggestion && suggestion.video_model && (
              <ReasonBadge
                reason={suggestion.video_reason}
                applied={applied && genSettings.videoModel === suggestion.video_model}
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}
