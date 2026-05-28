import { useState, useCallback } from 'react';
import { sendChatMessage } from '../services';
import { makeId } from '../utils/helpers';
import { getOnboardingData, saveOnboardingData } from '../utils/storage';

export default function useChat() {
  const [messages, setMessages] = useState([]);
  const [history, setHistory] = useState([]);
  const [context, setContext] = useState(null);
  const [pendingSlots, setPendingSlots] = useState(null);
  const [filledSlots, setFilledSlots] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);

  const addUserMessage = (text) => {
    const msg = { id: makeId(), role: 'user', text };
    setMessages((prev) => [...prev, msg]);
    return msg;
  };

  const addAssistantMessage = (response) => {
    const msg = {
      id: makeId(),
      role: 'assistant',
      text: response.message,
      isConfirmation: response.is_confirmation ?? false,
      inferred_summary: response.inferred_summary ?? null,
      isClarification: response.needs_clarification ?? false,
      clarification_question: response.clarification_question ?? null,
      choices: response.clarification_choices ?? null,
      pending_slots: response.pending_slots ?? null,
      hasResults: response.ready_for_rag && !!response.search_results,
      search_results: response.search_results ?? null,
      also_results: response.also_results ?? null,
      availability_index: response.availability_index ?? null,
      follow_up_choices: response.follow_up_choices ?? null,
      error: response.error ?? null,
    };
    setMessages((prev) => [...prev, msg]);
    return msg;
  };

  const callApi = useCallback(async (query, apiParams = {}) => {
    setIsLoading(true);
    try {
      const response = await sendChatMessage({
        query,
        history,
        context,
        user_profile: getOnboardingData(),
        session_id: sessionId,
        ...apiParams,
      });

      setContext(response.context ?? null);
      setPendingSlots(response.pending_slots ?? null);
      setFilledSlots(response.filled_slots ?? []);
      if (response.session_id) setSessionId(response.session_id);

      setHistory((prev) => [
        ...prev,
        { role: 'user', content: query },
        { role: 'assistant', content: response.message },
      ]);

      addAssistantMessage(response);

      if (response.filled_slots?.length > 0) {
        saveOnboardingData({
          filled_slots: response.filled_slots,
          context: response.context,
        });
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { id: makeId(), role: 'assistant', text: `오류가 발생했습니다: ${err.message}`, error: err.message },
      ]);
    } finally {
      setIsLoading(false);
    }
  }, [history, context]);

  const sendMessage = useCallback((text) => {
    if (!text.trim() || isLoading) return;
    addUserMessage(text);
    callApi(text, { pending_slots: pendingSlots });
  }, [callApi, isLoading, pendingSlots]);

  const selectChoice = useCallback((choice, slots) => {
    const displayText = choice.label ?? choice.text ?? JSON.stringify(choice);
    addUserMessage(displayText);
    callApi(displayText, { selected_choice: choice, pending_slots: slots ?? pendingSlots });
  }, [callApi, pendingSlots]);

  const confirmInferred = useCallback((confirmed) => {
    const text = confirmed ? '맞아요, 진행해 주세요' : '수정할게요';
    addUserMessage(text);
    callApi(text, { confirm_inferred: confirmed, pending_slots: confirmed ? null : pendingSlots });
  }, [callApi, pendingSlots]);

  const resetChat = useCallback(() => {
    setMessages([]);
    setHistory([]);
    setContext(null);
    setPendingSlots(null);
    setFilledSlots([]);
    setSessionId(null);
  }, []);

  // 이전 세션 불러오기
  const loadSession = useCallback((session) => {
    const uiMessages = (session.messages || []).map((m) => ({ ...m, id: makeId() }));
    setMessages(uiMessages);
    setHistory(session.history || []);
    setContext(session.context ?? null);
    setPendingSlots(session.pending_slots ?? null);
    setFilledSlots([]);
    setSessionId(session.id);
  }, []);

  return { messages, filledSlots, isLoading, sessionId, sendMessage, selectChoice, confirmInferred, resetChat, loadSession };
}
