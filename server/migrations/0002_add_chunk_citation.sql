-- 답변에 붙일 출처 문자열(예: "근로기준법 제60조 제1항~제3항")을 조각에 저장한다.
-- 기존 행이 있어도 적용되도록 빈 문자열 기본값으로 추가한 뒤 기본값을 없앤다.
ALTER TABLE chunks ADD COLUMN citation text NOT NULL DEFAULT '';
ALTER TABLE chunks ALTER COLUMN citation DROP DEFAULT;
